"""Orquestra o pipeline completo: roteiro -> narração -> cenas -> imagens -> legenda -> vídeo final.

Um único fluxo pra tudo: vídeo narrado normal, com ou sem som de fundo
(chuva/música bem baixa por baixo da narração), ou sem narração nenhuma (só o
som de fundo + imagem, pra vídeos longos de relaxar/dormir)."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from engine import ambiente, canal, render, roteiro as roteiro_mod, scenes, subtitles, thumbnail as thumbnail_mod, tts, visuals
from engine.roteiro import PALAVRAS_POR_MINUTO

RAIZ_SAIDA = Path(__file__).resolve().parent.parent / "output"

# Ajustes de legenda por formato: no Shorts (9:16) a tela é mais estreita,
# então usamos fonte menor e a legenda mais perto da borda inferior, pra
# sobrar mais espaço de imagem visível.
ESTILO_LEGENDA_POR_FORMATO = {
    "16:9": {"largura": 1920, "altura": 1080, "fontsize": 82, "marginv": 55, "palavras_por_legenda": 6},
    "9:16": {"largura": 1080, "altura": 1920, "fontsize": 62, "marginv": 130, "palavras_por_legenda": 5},
}

# Sem narração: uma imagem nova a cada tantos segundos — bem calmo, não troca
# como se fosse uma cena narrada.
SEGUNDOS_POR_IMAGEM_SEM_NARRACAO = 240

VOLUME_SOM_DE_FUNDO = 0.2  # por baixo da narração, propositalmente baixo


def _slug(texto: str) -> str:
    texto = texto.strip().lower()
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    return texto.strip("-")[:60] or "video"


@dataclass
class ResultadoGeracao:
    pasta: Path
    audio: Path
    video_16_9: Path
    video_9_16: Path
    duracao_segundos: float
    roteiro: str
    tags: list = field(default_factory=list)
    thumbnail: Path | None = None


def _salvar_metadados(pasta: Path, **campos) -> None:
    caminho = pasta / "metadata.json"
    dados = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
    dados.update(campos)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def gerar_video(
    titulo: str,
    roteiro: str | None = None,
    idioma: str = "pt-BR",
    voz: str = "mulher",
    estilo_imagem: str = "procedural",
    duracao_alvo_minutos: float | None = None,
    descricao_video: str = "",
    data_postagem: str | None = None,
    sem_narracao: bool = False,
    som_fundo_tipo: str = "",
    som_fundo_descricao: str = "",
    canal_id: str | None = None,
    progresso: Callable[[str, float], None] | None = None,
) -> ResultadoGeracao:
    """sem_narracao=True: vídeo é só o som de fundo (som_fundo_tipo, "chuva"
    por padrão) + imagem, sem roteiro/voz/legenda — pensado pra vídeos longos.
    sem_narracao=False (padrão): vídeo narrado normal; som_fundo_tipo opcional
    mistura um som de fundo bem baixo por baixo da narração.
    canal_id: de qual canal é esse vídeo (contexto usado pro roteiro automático
    e conta do YouTube usada na publicação); None = canal ativo no momento."""

    canal_id = canal_id or canal.canal_ativo_id()

    def avisar(etapa: str, percentual: float) -> None:
        if progresso is not None:
            progresso(etapa, percentual)

    pasta = RAIZ_SAIDA / _slug(titulo)
    pasta.mkdir(parents=True, exist_ok=True)
    _salvar_metadados(
        pasta,
        titulo=titulo,
        data_postagem=data_postagem,
        descricao_video=descricao_video,
        sem_narracao=sem_narracao,
        som_fundo_tipo=som_fundo_tipo,
        som_fundo_descricao=som_fundo_descricao,
        idioma=idioma,
        voz=voz,
        estilo_imagem=estilo_imagem,
        duracao_alvo_minutos=duracao_alvo_minutos,
        canal_id=canal_id,
    )

    tags: list = []

    if sem_narracao:
        # --- sem fala: o som de fundo É o áudio do vídeo inteiro ---
        duracao_real = (duracao_alvo_minutos or 15.0) * 60
        tipo_efetivo = som_fundo_tipo or "chuva"
        avisar(f"Gerando o som de fundo ({tipo_efetivo})", 15)
        audio_path = pasta / "audio.wav"
        ambiente.gerar_som_ambiente(tipo_efetivo, duracao_real, audio_path, descricao=som_fundo_descricao)
        submaker = None
        roteiro_final = ""
    else:
        # --- com fala: roteiro + narração, som de fundo é opcional e mixado por baixo ---
        if roteiro is None:
            avisar("Escrevendo o roteiro", 3)
            # o contexto do canal é sempre levado em conta aqui, como base — não
            # precisa repetir isso na descrição de cada vídeo.
            roteiro = roteiro_mod.gerar_roteiro(
                titulo,
                duracao_alvo_minutos or 1.0,
                contexto_canal=canal.obter_contexto(canal_id),
                descricao_video=descricao_video,
            )
            print(f"[roteiro gerado]\n{roteiro}\n")
        roteiro_final = roteiro
        # salva sempre (gerado por IA ou colado por você) — é o que permite o
        # "Regenerar" manter o mesmo roteiro depois, em vez de escrever um novo
        (pasta / "roteiro.txt").write_text(roteiro_final, encoding="utf-8")

        avisar("Gerando a narração", 8)
        narracao_path = pasta / "narracao.mp3"
        submaker = tts.sintetizar(roteiro, idioma, voz, narracao_path)

        duracao_real = (submaker.cues[-1].end - submaker.cues[0].start).total_seconds()
        if duracao_alvo_minutos is not None:
            alvo_segundos = duracao_alvo_minutos * 60
            if duracao_real < alvo_segundos * 0.9:
                palavras_faltando = round((alvo_segundos - duracao_real) / 60 * PALAVRAS_POR_MINUTO)
                print(
                    f"[aviso] roteiro dá ~{duracao_real / 60:.1f} min, abaixo da meta de "
                    f"{duracao_alvo_minutos:.1f} min. Escreva mais ~{palavras_faltando} palavras "
                    f"({PALAVRAS_POR_MINUTO} palavras/min é a média dessa narração)."
                )
            elif duracao_real > alvo_segundos * 1.1:
                print(
                    f"[aviso] roteiro dá ~{duracao_real / 60:.1f} min, acima da meta de "
                    f"{duracao_alvo_minutos:.1f} min. Considere cortar texto."
                )

        avisar("Gerando hashtags", 12)
        try:
            tags = roteiro_mod.gerar_hashtags(titulo, roteiro)
            (pasta / "tags.txt").write_text(", ".join(tags), encoding="utf-8")
        except RuntimeError as erro:
            print(f"[aviso] geração de hashtags falhou, seguindo sem elas: {erro}")
            tags = []

        if som_fundo_tipo:
            avisar(f"Gerando o som de fundo ({som_fundo_tipo})", 14)
            som_fundo_path = pasta / "som_fundo.wav"
            ambiente.gerar_som_ambiente(som_fundo_tipo, duracao_real, som_fundo_path, descricao=som_fundo_descricao)
            avisar("Misturando o som de fundo", 16)
            audio_path = render.mixar_audio_com_fundo(
                narracao_path, som_fundo_path, pasta / "audio_final.m4a", VOLUME_SOM_DE_FUNDO
            )
        else:
            audio_path = narracao_path

    # --- cenas/imagens: com narração, uma cena por frase; sem narração, imagens em intervalo fixo ---
    if sem_narracao:
        n_imagens = max(1, round(duracao_real / SEGUNDOS_POR_IMAGEM_SEM_NARRACAO))
        duracao_por_imagem = duracao_real / n_imagens
        contexto_cena = f"{titulo}. {descricao_video}".strip(". ") or titulo
        lista_cenas = [(contexto_cena, duracao_por_imagem) for _ in range(n_imagens)]
    else:
        avisar("Dividindo o roteiro em cenas", 18)
        cenas_obj = scenes.dividir_em_cenas(submaker, roteiro_final)
        lista_cenas = [(c.texto, c.duracao_segundos) for c in cenas_obj]

    # guardado pra dar pra regenerar uma cena específica depois (regenerar_cena),
    # sem precisar refazer roteiro/narração/outras cenas
    _salvar_metadados(
        pasta,
        cenas=[{"texto": texto, "duracao_segundos": duracao} for texto, duracao in lista_cenas],
        audio_arquivo=audio_path.name,
    )

    total_imagens = len(lista_cenas) * len(ESTILO_LEGENDA_POR_FORMATO)
    imagens_feitas = 0

    videos = {}
    for formato, estilo in ESTILO_LEGENDA_POR_FORMATO.items():
        sufixo = formato.replace(":", "x")
        legenda_path = None
        if not sem_narracao:
            legenda_path = subtitles.gerar_ass(submaker, pasta / f"legenda_{sufixo}.ass", roteiro=roteiro_final, **estilo)

        imagens_com_duracao = []
        for i, (texto_cena, duracao_cena) in enumerate(lista_cenas):
            caminho_imagem = pasta / f"cena{i:02d}_{sufixo}.png"
            try:
                visuals.gerar_fundo(
                    estilo_imagem,
                    estilo["largura"],
                    estilo["altura"],
                    caminho_imagem,
                    cena=texto_cena,
                    estilo_extra=descricao_video,
                )
            except RuntimeError as erro:
                # Fonte externa (foto/ia) falhou (rede, serviço fora do ar) — não
                # trava o vídeo inteiro por causa de uma cena, usa o procedural.
                print(f"[aviso] cena {i} ({estilo_imagem}) falhou, usando procedural: {erro}")
                visuals.gerar_fundo_procedural(estilo["largura"], estilo["altura"], caminho_imagem, semente=texto_cena)
            imagens_com_duracao.append((caminho_imagem, duracao_cena))

            imagens_feitas += 1
            avisar(f"Gerando imagens ({formato})", 20 + 65 * imagens_feitas / total_imagens)

        avisar(f"Montando o vídeo ({formato})", 88 if formato == "16:9" else 94)
        videos[formato] = render.renderizar_slideshow(
            imagens_com_duracao, audio_path, legenda_path, formato, pasta / f"video_{sufixo}.mp4"
        )

    avisar("Gerando a thumbnail", 97)
    caminho_thumb = thumbnail_mod.gerar_thumbnail(pasta / "cena00_16x9.png", titulo, pasta / "thumbnail.png")

    avisar("Pronto", 100)
    return ResultadoGeracao(pasta, audio_path, videos["16:9"], videos["9:16"], duracao_real, roteiro_final, tags, caminho_thumb)


def regenerar_cena(slug: str, indice: int, progresso: Callable[[str, float], None] | None = None) -> dict:
    """Refaz só a imagem de UMA cena (a IA sorteia de novo) e remonta o vídeo
    final com as imagens das outras cenas intactas — não mexe em roteiro,
    narração nem legenda. Só funciona em vídeos gerados depois desse recurso
    existir (precisa do metadata.json ter "cenas" salvo)."""

    def avisar(etapa: str, percentual: float) -> None:
        if progresso is not None:
            progresso(etapa, percentual)

    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        raise RuntimeError("Vídeo não encontrado.")

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    cenas = metadados.get("cenas")
    if not cenas:
        raise RuntimeError(
            "Esse vídeo foi gerado antes desse recurso existir — clique em "
            '"Regenerar" uma vez pra habilitar a edição por cena.'
        )
    if not (0 <= indice < len(cenas)):
        raise RuntimeError(f"Cena {indice} não existe (esse vídeo tem {len(cenas)} cenas).")

    audio_nome = metadados.get("audio_arquivo")
    audio_path = pasta / audio_nome if audio_nome else None
    if audio_path is None or not audio_path.exists():
        raise RuntimeError("Áudio original não encontrado — regenere o vídeo inteiro uma vez.")

    estilo_imagem = metadados.get("estilo_imagem", "procedural")
    descricao_video = metadados.get("descricao_video", "")
    sem_narracao = metadados.get("sem_narracao", False)
    texto_cena = cenas[indice]["texto"]

    total_passos = len(ESTILO_LEGENDA_POR_FORMATO) * 2  # gerar imagem + remontar, por formato
    passo = 0
    thumbnail_atualizada = False
    nomes_video = {}

    for formato, estilo in ESTILO_LEGENDA_POR_FORMATO.items():
        sufixo = formato.replace(":", "x")
        caminho_imagem = pasta / f"cena{indice:02d}_{sufixo}.png"

        passo += 1
        avisar(f"Gerando nova imagem da cena ({formato})", 10 + 80 * passo / total_passos)
        try:
            visuals.gerar_fundo(
                estilo_imagem, estilo["largura"], estilo["altura"], caminho_imagem,
                cena=texto_cena, estilo_extra=descricao_video,
            )
        except RuntimeError as erro:
            print(f"[aviso] cena {indice} ({estilo_imagem}) falhou, usando procedural: {erro}")
            visuals.gerar_fundo_procedural(estilo["largura"], estilo["altura"], caminho_imagem, semente=f"{texto_cena}-{passo}")

        passo += 1
        avisar(f"Remontando o vídeo ({formato})", 10 + 80 * passo / total_passos)
        imagens_com_duracao = []
        for i, cena in enumerate(cenas):
            img = pasta / f"cena{i:02d}_{sufixo}.png"
            if not img.exists():
                raise RuntimeError(f"Imagem da cena {i} sumiu do disco — regenere o vídeo inteiro uma vez.")
            imagens_com_duracao.append((img, cena["duracao_segundos"]))

        legenda_path = pasta / f"legenda_{sufixo}.ass"
        legenda_path = legenda_path if (not sem_narracao and legenda_path.exists()) else None

        caminho_video = pasta / f"video_{sufixo}.mp4"
        render.renderizar_slideshow(imagens_com_duracao, audio_path, legenda_path, formato, caminho_video)
        nomes_video[formato] = caminho_video.name

    if indice == 0:
        avisar("Atualizando a thumbnail", 95)
        texto_thumb = metadados.get("thumbnail_texto") or metadados.get("titulo", slug)
        cor_thumb = thumbnail_mod.cor_de_hex(metadados.get("thumbnail_cor", ""))
        posicao_thumb = metadados.get("thumbnail_posicao", "baixo-centro")
        tamanho_thumb = thumbnail_mod.TAMANHOS.get(metadados.get("thumbnail_tamanho", "medio"), 80)
        thumbnail_mod.gerar_thumbnail(pasta / "cena00_16x9.png", texto_thumb, pasta / "thumbnail.png", cor_thumb, posicao_thumb, tamanho_thumb)
        thumbnail_atualizada = True

    avisar("Pronto", 100)
    return {
        "video_16_9": nomes_video["16:9"],
        "video_9_16": nomes_video["9:16"],
        "thumbnail_atualizada": thumbnail_atualizada,
    }
