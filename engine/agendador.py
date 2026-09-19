"""Roda em segundo plano junto com o app: confere periodicamente os vídeos
com data de postagem vencida e publica sozinho no YouTube (16:9 como vídeo
normal, 9:16 como Short). Pra funcionar precisa de client_secret.json na raiz
do projeto e de uma conta conectada (engine.youtube.conectar)."""

import json
import threading
import time
from datetime import date, datetime
from pathlib import Path

from engine import canal as canal_mod
from engine import roteiro as roteiro_mod
from engine import thumbnail as thumbnail_mod
from engine import youtube
from engine.pipeline import RAIZ_SAIDA

INTERVALO_SEGUNDOS = 600  # confere a cada 10 min
PRIVACIDADE_PADRAO = "public"  # fallback só pra vídeo antigo, gerado antes desse campo existir


def _conta_youtube_do_video(metadados: dict) -> str:
    """Cada vídeo é de um canal (metadados["canal_id"]); publica na conta do
    YouTube própria desse canal. Vídeos de antes desse recurso existir não têm
    canal_id salvo — caem no canal padrão, mesmo comportamento de sempre."""
    canal_id = metadados.get("canal_id") or canal_mod.CANAL_PADRAO_ID
    canal = canal_mod.obter_canal(canal_id)
    return canal["conta_youtube"] if canal else canal_mod.CANAL_PADRAO_ID


def _salvar_metadados(caminho_meta: Path, metadados: dict) -> None:
    caminho_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")


def _thumbnail_shorts(pasta: Path, metadados: dict) -> Path | None:
    """Thumbnail vertical (1080x1920), com o que foi salvo no editor do Short."""
    return thumbnail_mod.gerar_shorts(pasta, metadados)


def _publicar_um(pasta: Path, metadados: dict, caminho_meta: Path, nome_conta: str) -> None:
    """Publica os dois formatos. Salva o ID de cada um assim que sobe — se o
    16:9 subir e o Short falhar (ou vice-versa), o próximo ciclo só tenta de
    novo o que faltou, nunca sobe o mesmo vídeo duas vezes."""
    v16, v9 = pasta / "video_16x9.mp4", pasta / "video_9x16.mp4"
    titulo = metadados.get("titulo", pasta.name)
    privacidade = metadados.get("privacidade") or PRIVACIDADE_PADRAO
    if privacidade not in ("private", "unlisted", "public"):
        privacidade = PRIVACIDADE_PADRAO

    tags_path = pasta / "tags.txt"
    tags = [t.strip() for t in tags_path.read_text(encoding="utf-8").split(",")] if tags_path.exists() else []
    roteiro_path = pasta / "roteiro.txt"
    descricao = metadados.get("descricao_youtube")
    if not descricao:
        # vídeo sem descrição própria (gerado antes desse recurso): escreve uma agora em vez de subir o roteiro inteiro
        texto_roteiro = roteiro_path.read_text(encoding="utf-8") if roteiro_path.exists() else titulo
        try:
            descricao = roteiro_mod.gerar_descricao(titulo, texto_roteiro, tags)
        except Exception:
            descricao = roteiro_mod.descricao_basica(titulo, texto_roteiro, tags)
        metadados["descricao_youtube"] = descricao
        _salvar_metadados(caminho_meta, metadados)

    descricao = roteiro_mod.com_hashtags(descricao, tags, titulo)  # as # entram sozinhas (você não precisa lembrar)

    if v16.exists() and not metadados.get("youtube_video_id"):
        id_normal = youtube.publicar_video(v16, titulo, descricao, tags, nome_conta, privacidade, is_short=False)
        metadados["youtube_video_id"] = id_normal
        _salvar_metadados(caminho_meta, metadados)
        print(f"[agendador] 16:9 publicado: {titulo} -> https://youtu.be/{id_normal}")

    thumb = pasta / "thumbnail.png"
    if metadados.get("youtube_video_id") and thumb.exists() and not metadados.get("thumbnail_enviada"):
        try:
            youtube.definir_thumbnail(nome_conta, metadados["youtube_video_id"], thumb)
            metadados["thumbnail_enviada"] = True
            print(f"[agendador] thumbnail enviada: {titulo}")
        except Exception as erro:
            # não trava a publicação: a causa comum é canal sem verificação por telefone
            print(f"[agendador] thumbnail não enviada ({titulo}): {erro}")
        _salvar_metadados(caminho_meta, metadados)

    if v9.exists() and not metadados.get("youtube_short_id"):
        id_short = youtube.publicar_video(v9, titulo, descricao, tags, nome_conta, privacidade, is_short=True)
        metadados["youtube_short_id"] = id_short
        _salvar_metadados(caminho_meta, metadados)
        print(f"[agendador] short publicado: {titulo} -> https://youtu.be/{id_short}")

    if metadados.get("youtube_short_id") and not metadados.get("thumbnail_short_enviada"):
        try:
            thumb_short = _thumbnail_shorts(pasta, metadados)
            if thumb_short:
                youtube.definir_thumbnail(nome_conta, metadados["youtube_short_id"], thumb_short)
                metadados["thumbnail_short_enviada"] = True
                print(f"[agendador] thumbnail do short enviada: {titulo}")
        except Exception as erro:
            print(f"[agendador] thumbnail do short não enviada ({titulo}): {erro}")
        _salvar_metadados(caminho_meta, metadados)

    metadados["publicado"] = True
    metadados.pop("publicacao_erro", None)
    _salvar_metadados(caminho_meta, metadados)


def publicar_pendentes() -> None:
    if not RAIZ_SAIDA.exists():
        return
    agora = datetime.now()
    hoje = agora.date().isoformat()

    for pasta in RAIZ_SAIDA.iterdir():
        if not pasta.is_dir():
            continue
        caminho_meta = pasta / "metadata.json"
        if not caminho_meta.exists():
            continue

        metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
        if metadados.get("publicado"):
            continue
        if not metadados.get("aprovado", False) or not metadados.get("editado", False):
            continue  # só sobe depois de você marcar "Editado" e confirmar a publicação na Fila

        data_postagem = metadados.get("data_postagem")
        if not data_postagem or data_postagem > hoje:
            continue  # ainda não chegou o dia
        hora_postagem = metadados.get("hora_postagem")
        if data_postagem == hoje and hora_postagem and agora.strftime("%H:%M") < hora_postagem:
            continue  # chegou o dia, mas ainda não a hora marcada

        v16, v9 = pasta / "video_16x9.mp4", pasta / "video_9x16.mp4"
        if not (v16.exists() or v9.exists()):
            continue  # geração ainda não terminou

        nome_conta = _conta_youtube_do_video(metadados)
        if not youtube.esta_conectado(nome_conta):
            metadados["publicacao_erro"] = f"Conta do YouTube do canal '{metadados.get('canal_id', canal_mod.CANAL_PADRAO_ID)}' não conectada — conecte na aba Canais."
            _salvar_metadados(caminho_meta, metadados)
            continue

        try:
            _publicar_um(pasta, metadados, caminho_meta, nome_conta)
        except Exception as erro:
            metadados["publicacao_erro"] = str(erro)
            _salvar_metadados(caminho_meta, metadados)
            print(f"[agendador] falha ao publicar '{metadados.get('titulo')}': {erro}")


def iniciar_agendador() -> None:
    def loop() -> None:
        while True:
            try:
                publicar_pendentes()
            except Exception as erro:
                print(f"[agendador] erro no ciclo: {erro}")
            time.sleep(INTERVALO_SEGUNDOS)

    threading.Thread(target=loop, daemon=True).start()
