"""Orquestra o pipeline completo: roteiro -> narração -> cenas -> imagens -> legenda -> vídeo final.

Um único fluxo pra tudo: vídeo narrado normal, com ou sem som de fundo
(chuva/música bem baixa por baixo da narração), ou sem narração nenhuma (só o
som de fundo + imagem, pra vídeos longos de relaxar/dormir)."""

import json
import threading
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from engine import ambiente, biblioteca, canal, midias, render, roteiro as roteiro_mod, scenes, subtitles, thumbnail as thumbnail_mod, tts, visuals
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


FORMATOS_ESCOLHA = {
    "ambos": ["16:9", "9:16"],
    "normal": ["16:9"],
    "shorts": ["9:16"],
}


def _formatos_de(formatos: str) -> dict:
    escolhidos = FORMATOS_ESCOLHA.get(formatos, FORMATOS_ESCOLHA["ambos"])
    return {f: e for f, e in ESTILO_LEGENDA_POR_FORMATO.items() if f in escolhidos}


slug_titulo = _slug  # nome público — usado pelo backend pra saber a pasta antes de disparar o job


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


def _derivar_16x9_do_vertical(pasta: Path, indice: int) -> None:
    """Vídeo só Shorts: o painel de cenas e a thumbnail trabalham com a imagem 16:9, então ela é derivada da
    vertical (sem gastar outra geração de IA) sempre que a cena muda."""
    vertical = pasta / f"cena{indice:02d}_9x16.png"
    if vertical.exists():
        visuals._cobrir(Image.open(vertical).convert("RGB"), 1920, 1080).save(pasta / f"cena{indice:02d}_16x9.png", "PNG")


def _imagem_de_cena_em_branco(caminho: Path, largura: int, altura: int, numero: int) -> None:
    """Quadro vazio de uma cena que você ainda vai montar: fundo escuro liso com o número da cena."""
    from PIL import ImageDraw, ImageFont

    imagem = Image.new("RGB", (largura, altura), (28, 27, 24))
    desenho = ImageDraw.Draw(imagem)

    def fonte(tamanho: int):
        for nome in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
            try:
                return ImageFont.truetype(nome, tamanho)
            except OSError:
                continue
        return ImageFont.load_default(tamanho)

    for texto, tamanho, cor, dy in ((f"Cena {numero}", altura // 7, (242, 194, 48), -altura // 12), ("Vazia: importe uma imagem ou vídeo", altura // 22, (170, 165, 150), altura // 10)):
        f = fonte(tamanho)
        caixa = desenho.textbbox((0, 0), texto, font=f)
        desenho.text(((largura - (caixa[2] - caixa[0])) / 2, altura / 2 + dy - (caixa[3] - caixa[1]) / 2), texto, font=f, fill=cor)
    imagem.save(caminho, "PNG")


def _gerar_em_branco(pasta: Path, titulo: str, formatos: str, num_cenas: int | None, duracao_alvo_minutos: float | None, transicao: str, legenda: dict | None, progresso) -> ResultadoGeracao:
    """Vídeo sem IA: só as cenas (no número escolhido), todas vazias e mudas, para você montar na Fila
    (escrever o texto de cada uma, importar imagem/vídeo, ajustar o tempo). Reaproveita a remontagem
    de "tempo das cenas" para gerar o áudio (silêncio) e o mp4."""
    import subprocess

    from engine.ferramentas import caminho_ffmpeg

    def avisar(etapa: str, pct: float) -> None:
        if progresso is not None:
            progresso(etapa, pct)

    n = max(1, min(int(num_cenas or 3), 40))
    por_cena = round(max(2.0, min(120.0, (duracao_alvo_minutos or 0.5) * 60 / n)), 1)
    avisar("Criando as cenas em branco", 10)
    narracao = pasta / "narracao.mp3"
    r = subprocess.run(
        [caminho_ffmpeg(), "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{por_cena * n:.2f}", "-c:a", "libmp3lame", "-q:a", "5", str(narracao)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ao criar o áudio vazio:\n{r.stderr[-800:]}")
    (pasta / "cues.json").write_text("[]", encoding="utf-8")
    (pasta / "roteiro.txt").write_text("", encoding="utf-8")
    formatos_ativos = _formatos_de(formatos)
    for k, (formato, estilo) in enumerate(formatos_ativos.items()):
        sufixo = formato.replace(":", "x")
        for i in range(n):
            (pasta / f"cena{i:02d}_{sufixo}.png").with_suffix(".mp4").unlink(missing_ok=True)
            _imagem_de_cena_em_branco(pasta / f"cena{i:02d}_{sufixo}.png", estilo["largura"], estilo["altura"], i + 1)
    if "16:9" not in formatos_ativos:
        for i in range(n):
            _derivar_16x9_do_vertical(pasta, i)
    _salvar_metadados(
        pasta,
        cenas=[{"texto": "", "duracao_segundos": por_cena, "duracao_natural": por_cena} for _ in range(n)],
        num_cenas=n, narracao_arquivo=narracao.name, audio_natural=narracao.name, audio_arquivo=narracao.name,
        imagens_base_cenas={}, videos_base_cenas={}, descricoes_cenas={},
        duracao_segundos=round(por_cena * n, 1),
    )
    resultado = aplicar_duracoes(pasta.name, {}, progresso=lambda etapa, pct: avisar(etapa, 20 + 0.75 * pct))
    avisar("Gerando a thumbnail", 97)
    caminho_thumb = thumbnail_mod.gerar_thumbnail(pasta / "cena00_16x9.png", titulo, pasta / "thumbnail.png")
    avisar("Pronto", 100)
    return ResultadoGeracao(pasta, pasta / "audio_ajustado.m4a", (pasta / "video_16x9.mp4") if resultado.get("video_16_9") else None, (pasta / "video_9x16.mp4") if resultado.get("video_9_16") else None, por_cena * n, "", [], caminho_thumb)


def _preparar_som_da_base(nome_unico: str, playlist: list | None, opcoes: dict | None, duracao: float, destino: Path) -> None:
    """Som de fundo vindo da Base: uma playlist de áudios (com tempo por áudio, transição suave e fade final)
    ou, sem playlist, o áudio único repetido em loop até o fim do vídeo."""
    opcoes = opcoes or {}
    itens = playlist or [{"nome": nome_unico, "segundos": None}]
    biblioteca.preparar_playlist_para_video(
        itens, duracao, destino,
        repetir=opcoes.get("repetir", "repetir") != "silencio",
        suave=bool(opcoes.get("suave", True)),
        fade_final=bool(opcoes.get("fade", True)),
    )


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
    hora_postagem: str | None = None,
    sem_narracao: bool = False,
    som_fundo_tipo: str = "",
    som_fundo_descricao: str = "",
    som_fundo_biblioteca: str = "",
    som_fundo_playlist: list | None = None,
    som_fundo_opcoes: dict | None = None,
    narracao_customizada: bool = False,
    privacidade: str = "public",
    formatos: str = "ambos",
    canal_id: str | None = None,
    num_cenas: int | None = None,
    imagens_base: list | None = None,
    base_restante: str = "estilo",
    transicao: str = "fade",
    legenda: dict | None = None,
    reaproveitar_imagens: bool = False,
    slug_pasta: str | None = None,
    em_branco: bool = False,
    descricao_youtube: str = "",
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

    pasta = RAIZ_SAIDA / (slug_pasta or _slug(titulo))  # regenerar mantém a pasta mesmo se o título foi renomeado
    pasta.mkdir(parents=True, exist_ok=True)
    _salvar_metadados(
        pasta,
        titulo=titulo,
        data_postagem=data_postagem,
        hora_postagem=hora_postagem or None,
        descricao_video=descricao_video,
        sem_narracao=sem_narracao,
        som_fundo_tipo=som_fundo_tipo,
        som_fundo_descricao=som_fundo_descricao,
        som_fundo_biblioteca=som_fundo_biblioteca,
        som_fundo_playlist=som_fundo_playlist or [],
        som_fundo_opcoes=som_fundo_opcoes or {},
        narracao_customizada=narracao_customizada,
        privacidade=privacidade,
        formatos=formatos,
        num_cenas=num_cenas,
        imagens_base=imagens_base or [],
        base_restante=base_restante,
        transicao=transicao,
        legenda=legenda or {},
        aprovado=False,  # só publica depois de você confirmar na Fila
        editado=False,   # vídeo (re)gerado do zero: a marca "Editado" volta a ser sua
        idioma=idioma,
        voz=voz,
        estilo_imagem=estilo_imagem,
        duracao_alvo_minutos=duracao_alvo_minutos,
        canal_id=canal_id,
        em_branco=em_branco,
        **({"descricao_youtube": descricao_youtube} if descricao_youtube.strip() else {}),  # escrita por você: a IA não sobrescreve
    )

    if em_branco:
        return _gerar_em_branco(pasta, titulo, formatos, num_cenas, duracao_alvo_minutos, transicao, legenda, progresso)

    tags: list = []

    if sem_narracao:
        # --- sem fala: o som de fundo É o áudio do vídeo inteiro ---
        duracao_real = (duracao_alvo_minutos or 15.0) * 60
        audio_path = pasta / "audio.wav"
        if som_fundo_tipo == "biblioteca" and som_fundo_biblioteca:
            avisar(f"Preparando o áudio da biblioteca ({som_fundo_biblioteca})", 15)
            _preparar_som_da_base(som_fundo_biblioteca, som_fundo_playlist, som_fundo_opcoes, duracao_real, audio_path)
        else:
            tipo_efetivo = som_fundo_tipo or "chuva"
            avisar(f"Gerando o som de fundo ({tipo_efetivo})", 15)
            ambiente.gerar_som_ambiente(tipo_efetivo, duracao_real, audio_path, descricao=som_fundo_descricao)
        submaker = None
        roteiro_final = ""
    else:
        # --- com fala: roteiro + narração, som de fundo é opcional e mixado por baixo ---
        if narracao_customizada and not roteiro:
            raise ValueError(
                "Narração gravada por você precisa do roteiro (o texto que você leu) — "
                "sem ele não dá pra sincronizar cenas nem legenda."
            )

        if roteiro is None:
            avisar("Escrevendo o roteiro", 3)
            # o contexto do canal é sempre levado em conta aqui, como base — não
            # precisa repetir isso na descrição de cada vídeo.
            roteiro = roteiro_mod.gerar_roteiro(
                titulo,
                duracao_alvo_minutos or 1.0,
                contexto_canal=canal.obter_contexto(canal_id),
                descricao_video=descricao_video,
                num_cenas=num_cenas,
                cenas_midia=midias.descricoes_para_roteiro(imagens_base),
            )
            print(f"[roteiro gerado]\n{roteiro}\n")
        roteiro_final = roteiro
        # salva sempre (gerado por IA ou colado por você) — é o que permite o
        # "Regenerar" manter o mesmo roteiro depois, em vez de escrever um novo
        (pasta / "roteiro.txt").write_text(roteiro_final, encoding="utf-8")

        if narracao_customizada:
            # o áudio já foi salvo (e validado/reencodado) pelo backend antes
            # de disparar esse job, como pasta/"narracao_custom.mp3"
            avisar("Lendo a narração enviada por você", 8)
            narracao_path = pasta / "narracao_custom.mp3"
            if not narracao_path.exists():
                raise ValueError("Não achei o áudio de narração enviado — tenta gravar/enviar de novo.")
            duracao_real = tts.duracao_do_audio(narracao_path)
            # sem timestamp real por palavra (isso só o TTS local dá) — aproxima
            # um ritmo de fala constante pra cenas/legenda ainda funcionarem
            submaker = tts.submaker_aproximado(roteiro_final, duracao_real)
        else:
            avisar("Gerando a narração", 8)
            narracao_path = pasta / "narracao.mp3"
            submaker = tts.sintetizar(roteiro, idioma, voz, narracao_path)
            duracao_real = (submaker.cues[-1].end - submaker.cues[0].start).total_seconds()

        if not narracao_customizada and duracao_alvo_minutos is not None:
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

        # descrição do YouTube: se o roteiro não mudou e já existe uma (ou você/o agente editou), mantém
        try:
            meta_atual = json.loads((pasta / "metadata.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta_atual = {}
        roteiro_antigo = (pasta / "roteiro.txt").read_text(encoding="utf-8") if (pasta / "roteiro.txt").exists() else None
        if not (meta_atual.get("descricao_youtube") and roteiro_antigo == roteiro_final):
            avisar("Escrevendo a descrição do YouTube", 13)
            _salvar_metadados(pasta, descricao_youtube=roteiro_mod.gerar_descricao(titulo, roteiro_final, tags, canal.obter_contexto(canal_id)))

        if som_fundo_tipo:
            som_fundo_path = pasta / "som_fundo.wav"
            if som_fundo_tipo == "biblioteca" and som_fundo_biblioteca:
                avisar(f"Preparando o som de fundo ({som_fundo_biblioteca})", 14)
                _preparar_som_da_base(som_fundo_biblioteca, som_fundo_playlist, som_fundo_opcoes, duracao_real, som_fundo_path)
            else:
                avisar(f"Gerando o som de fundo ({som_fundo_tipo})", 14)
                ambiente.gerar_som_ambiente(som_fundo_tipo, duracao_real, som_fundo_path, descricao=som_fundo_descricao)
            avisar("Misturando o som de fundo", 16)
            audio_path = render.mixar_audio_com_fundo(
                narracao_path, som_fundo_path, pasta / "audio_final.m4a", VOLUME_SOM_DE_FUNDO
            )
        else:
            audio_path = narracao_path

    # --- cenas/imagens: com narração, uma cena por frase; sem narração, imagens em intervalo fixo ---
    if sem_narracao:
        n_imagens = num_cenas or max(1, round(duracao_real / SEGUNDOS_POR_IMAGEM_SEM_NARRACAO))
        duracao_por_imagem = duracao_real / n_imagens
        contexto_cena = f"{titulo}. {descricao_video}".strip(". ") or titulo
        lista_cenas = [(contexto_cena, duracao_por_imagem) for _ in range(n_imagens)]
    else:
        avisar("Dividindo o roteiro em cenas", 18)
        cenas_obj = scenes.dividir_em_cenas(submaker, roteiro_final, num_cenas=num_cenas)
        lista_cenas = [(c.texto, c.duracao_segundos) for c in cenas_obj]

    # uma chamada de IA lê o roteiro todo e decide a imagem de cada cena (busca em inglês + descrição para você ver/corrigir)
    plano_visual: dict = {}
    if not sem_narracao and estilo_imagem in ("foto", "video", "ia"):
        if reaproveitar_imagens:
            try:
                plano_visual = json.loads((pasta / "metadata.json").read_text(encoding="utf-8")).get("plano_visual") or {}
            except (OSError, ValueError):
                plano_visual = {}
        else:
            avisar("Planejando a imagem de cada cena", 19)
            plano_visual = visuals.planejar_visuais(titulo, [t for t, _ in lista_cenas], descricao_video)
    _salvar_metadados(pasta, plano_visual=plano_visual)

    if submaker is not None:
        (pasta / "cues.json").write_text(
            json.dumps([{"start": c.start.total_seconds(), "end": c.end.total_seconds(), "content": c.content} for c in submaker.cues], ensure_ascii=False),
            encoding="utf-8",
        )

    # refazendo por causa de texto editado: as cenas cujo texto não mudou mantêm a imagem que já tinham
    cenas_mantidas = set()
    mapa_base_antigo = {}
    meta_antiga_videos = {}
    if reaproveitar_imagens:
        try:
            meta_antiga = json.loads((pasta / "metadata.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta_antiga = {}
        antigas = meta_antiga.get("cenas") or []
        mapa_base_antigo = meta_antiga.get("imagens_base_cenas") or {}
        meta_antiga_videos = meta_antiga.get("videos_base_cenas") or {}
        for i, (texto_c, _) in enumerate(lista_cenas):
            if i < len(antigas) and antigas[i].get("texto", "").strip() == texto_c.strip():
                cenas_mantidas.add(i)

    # imagens da Base escolhidas de antemão: a 1ª vai na cena 1, a 2ª na cena 2...
    escolhidas = midias.analisar_entradas(imagens_base)  # [("imagem"|"video", nome)] na ordem das cenas
    midia_por_cena = {}
    if escolhidas and not reaproveitar_imagens:
        if base_restante == "repetir":  # vídeo todo da Base: as escolhidas se repetem em ciclo
            midia_por_cena = {i: escolhidas[i % len(escolhidas)] for i in range(len(lista_cenas))}
        else:
            midia_por_cena = {i: m for i, m in enumerate(escolhidas[: len(lista_cenas)])}

    # guardado pra dar pra regenerar uma cena específica depois (regenerar_cena),
    # sem precisar refazer roteiro/narração/outras cenas
    _salvar_metadados(
        pasta,
        cenas=[{"texto": texto, "duracao_segundos": duracao, "duracao_natural": duracao} for texto, duracao in lista_cenas],
        narracao_arquivo=(narracao_path.name if not sem_narracao else ""),
        audio_natural=audio_path.name,
        videos_base_cenas=(
            {k: v for k, v in (meta_antiga_videos or {}).items() if int(k) in cenas_mantidas}
            if reaproveitar_imagens else {str(i): n for i, (tp, n) in midia_por_cena.items() if tp == "video"}
        ),
        imagens_base_cenas=(
            {k: v for k, v in mapa_base_antigo.items() if int(k) in cenas_mantidas}
            if reaproveitar_imagens else {str(i): n for i, (tp, n) in midia_por_cena.items() if tp == "imagem"}
        ),
        audio_arquivo=audio_path.name,
        duracao_segundos=round(duracao_real, 1),
    )

    formatos_ativos = _formatos_de(formatos)
    total_imagens = len(lista_cenas) * len(formatos_ativos)
    imagens_feitas = 0

    videos = {}
    for formato, estilo in formatos_ativos.items():
        sufixo = formato.replace(":", "x")
        legenda_path = None
        if not sem_narracao and (legenda or {}).get("modo") != "nenhuma":
            legenda_path = subtitles.gerar_ass(submaker, pasta / f"legenda_{sufixo}.ass", roteiro=roteiro_final, config=legenda, **estilo)

        imagens_com_duracao = []
        for i, (texto_cena, duracao_cena) in enumerate(lista_cenas):
            caminho_imagem = pasta / f"cena{i:02d}_{sufixo}.png"
            if i not in cenas_mantidas:
                caminho_imagem.with_suffix(".mp4").unlink(missing_ok=True)  # sobra de um vídeo antigo nessa cena
            if i in cenas_mantidas and caminho_imagem.exists():
                imagens_com_duracao.append((caminho_imagem, duracao_cena))
                imagens_feitas += 1
                avisar(f"Gerando imagens ({formato})", 20 + 65 * imagens_feitas / total_imagens)
                continue
            if i in midia_por_cena:
                tipo_m, nome_m = midia_por_cena[i]
                if tipo_m == "video":  # vídeo da Base nessa cena: recortado no formato, em loop se a cena for mais longa
                    render.preparar_clip(biblioteca.caminho_video_valido(nome_m), estilo["largura"], estilo["altura"], caminho_imagem.with_suffix(".mp4"), caminho_imagem, max_segundos=int(duracao_cena) + 5)
                else:
                    base_img = Image.open(biblioteca.caminho_imagem_valida(nome_m)).convert("RGB")
                    visuals._cobrir(base_img, estilo["largura"], estilo["altura"]).save(caminho_imagem, "PNG")
                imagens_com_duracao.append((caminho_imagem, duracao_cena))
                imagens_feitas += 1
                avisar(f"Gerando imagens ({formato})", 20 + 65 * imagens_feitas / total_imagens)
                continue
            try:
                visuals.gerar_fundo(
                    estilo_imagem,
                    estilo["largura"],
                    estilo["altura"],
                    caminho_imagem,
                    cena=texto_cena,
                    estilo_extra=descricao_video,
                    contexto=titulo,
                    duracao=duracao_cena,
                    plano=plano_visual.get(str(i)),
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
            imagens_com_duracao, audio_path, legenda_path, formato, pasta / f"video_{sufixo}.mp4", transicao=transicao
        )

    if "16:9" not in videos:
        # só Shorts: as telas de thumbnail/cenas trabalham com as imagens
        # 16:9, então deriva elas das verticais (sem gastar mais chamadas de IA)
        for i in range(len(lista_cenas)):
            vertical = Image.open(pasta / f"cena{i:02d}_9x16.png")
            visuals._cobrir(vertical, 1920, 1080).save(pasta / f"cena{i:02d}_16x9.png", "PNG")

    avisar("Gerando a thumbnail", 97)
    caminho_thumb = thumbnail_mod.gerar_thumbnail(pasta / "cena00_16x9.png", titulo, pasta / "thumbnail.png")

    avisar("Pronto", 100)
    return ResultadoGeracao(pasta, audio_path, videos.get("16:9"), videos.get("9:16"), duracao_real, roteiro_final, tags, caminho_thumb)


_travas_de_video: dict = {}
_travas_lock = threading.Lock()


_travas_de_edicao: dict = {}


def _com_trava_de_edicao(funcao):
    """Decorator: serializa as edições estruturais (tempos, cenas, legenda) do MESMO vídeo. RLock porque uma
    edição chama outra (editar_estrutura -> aplicar_duracoes)."""
    import functools

    @functools.wraps(funcao)
    def embrulhada(slug, *args, **kwargs):
        with _travas_lock:
            trava = _travas_de_edicao.setdefault(slug, threading.RLock())
        with trava:
            return funcao(slug, *args, **kwargs)

    return embrulhada


def _trava_do_video(slug: str) -> "threading.Lock":
    """Várias cenas do mesmo vídeo podem gerar a imagem ao mesmo tempo, mas a
    remontagem do mp4 é uma de cada vez (senão duas escrevem o mesmo arquivo)."""
    with _travas_lock:
        return _travas_de_video.setdefault(slug, threading.Lock())


VELOCIDADE_MAXIMA_FALA = 1.5  # encurtar uma cena acelera a fala dela, até 1,5x (acima disso fica corrido demais)


def _cues_ajustados(pasta: Path, metadados: dict) -> list:
    """Tempos das palavras da narração já ajustados aos tempos de cada cena: cena alongada = pausa
    depois da fala; cena encurtada = fala mais rápida. Cada cena começa onde a anterior termina."""
    from datetime import timedelta
    from types import SimpleNamespace

    cenas = metadados.get("cenas") or []
    naturais = [c.get("duracao_natural", c["duracao_segundos"]) for c in cenas]
    novos = [c["duracao_segundos"] for c in cenas]
    ini_natural, ini_novo = [0.0], [0.0]
    for n, d in zip(naturais, novos):
        ini_natural.append(ini_natural[-1] + n)
        ini_novo.append(ini_novo[-1] + d)

    def converter(t: float) -> float:
        idx = 0
        for i in range(len(naturais)):
            if ini_natural[i] <= t + 1e-6:
                idx = i
        fator = novos[idx] / naturais[idx] if novos[idx] < naturais[idx] - 0.05 else 1.0  # só encurtar muda o ritmo
        return ini_novo[idx] + (t - ini_natural[idx]) * fator

    dados = json.loads((pasta / "cues.json").read_text(encoding="utf-8"))
    return [
        SimpleNamespace(start=timedelta(seconds=converter(c["start"])), end=timedelta(seconds=converter(c["end"])), content=c["content"])
        for c in dados
    ]


@_com_trava_de_edicao
def aplicar_duracoes(slug: str, duracoes: dict, progresso: Callable[[str, float], None] | None = None) -> dict:
    """Muda o tempo de cada cena. As outras cenas NUNCA mudam de duração por causa disso: só andam pra
    frente (cena alongada) ou pra trás (cena encurtada). Alongar vira uma pausa depois da fala daquela
    cena; encurtar acelera a fala dela (até 1,5x). Refaz o áudio (com o som de fundo), a legenda e os vídeos."""
    import subprocess

    from engine.ferramentas import caminho_ffmpeg

    def avisar(etapa: str, pct: float) -> None:
        if progresso is not None:
            progresso(etapa, pct)

    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        raise RuntimeError("Vídeo não encontrado.")
    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    if metadados.get("sem_narracao"):
        raise RuntimeError("Vídeo sem narração: o tempo de cada cena já é o da imagem.")
    cenas = metadados.get("cenas") or []
    narracao = pasta / (metadados.get("narracao_arquivo") or "narracao.mp3")
    if not narracao.exists():
        narracao = pasta / "narracao_custom.mp3"
    if not cenas or not narracao.exists() or not (pasta / "cues.json").exists():
        raise RuntimeError('Esse vídeo foi gerado antes do tempo das cenas ser editável — use "Regenerar" uma vez para habilitar.')

    for i, c in enumerate(cenas):
        natural = c.get("duracao_natural", c["duracao_segundos"])
        c["duracao_natural"] = natural
        desejado = float(duracoes.get(str(i), duracoes.get(i, c["duracao_segundos"])))
        c["duracao_segundos"] = round(max(natural / VELOCIDADE_MAXIMA_FALA, 1.0, min(desejado, natural + 300)), 2)
        if c.get("audio_do_video"):
            c["duracao_segundos"] = natural  # vídeo com som próprio: não estica nem acelera
    naturais = [c["duracao_natural"] for c in cenas]
    novos = [c["duracao_segundos"] for c in cenas]
    extras = [round(d - n, 3) for d, n in zip(novos, naturais)]

    # --- áudio: narração original com uma pausa depois de cada cena que ganhou tempo ---
    avisar("Refazendo o áudio com as pausas", 10)
    natural_audio = metadados.get("audio_natural") or metadados.get("audio_arquivo")
    if True:  # sempre refaz: o áudio final nunca é reaproveitado (pode ter pausas de uma edição anterior)
        filtros, t, n = [], 0.0, len(cenas)
        for i, (nat, ext) in enumerate(zip(naturais, extras)):
            inicio = t
            t += nat
            trecho = f"atrim=start={inicio:.3f}" + (f":end={t:.3f}" if i < n - 1 else "")
            if ext > 0.01:
                ajuste = f",apad=pad_dur={ext:.3f}"  # cena mais longa: pausa depois da fala
            elif ext < -0.01:
                ajuste = f",atempo={nat / novos[i]:.4f}"  # cena mais curta: fala mais rápida (mesmo tom)
            else:
                ajuste = ""
            filtros.append(f"[0:a]{trecho},asetpts=PTS-STARTPTS{ajuste}[a{i}]")
        filtros.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[saida]")
        com_pausas = pasta / "narracao_com_pausas.wav"
        r = subprocess.run(
            [caminho_ffmpeg(), "-y", "-i", str(narracao), "-filter_complex", ";".join(filtros), "-map", "[saida]", "-ar", "44100", "-ac", "2", str(com_pausas)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"FFmpeg falhou ao inserir as pausas:\n{r.stderr[-1500:]}")
        final = pasta / "audio_ajustado.m4a"
        som_fundo = pasta / "som_fundo.wav"
        if metadados.get("som_fundo_tipo") == "biblioteca" and (metadados.get("som_fundo_playlist") or metadados.get("som_fundo_biblioteca")):
            avisar("Ajustando o som de fundo ao novo tamanho", 12)
            _preparar_som_da_base(metadados.get("som_fundo_biblioteca", ""), metadados.get("som_fundo_playlist"), metadados.get("som_fundo_opcoes"), sum(novos), som_fundo)
        if metadados.get("som_fundo_tipo") and som_fundo.exists():
            # nas cenas com o áudio do próprio vídeo (ex.: introdução com música) o som de fundo fica mudo
            trechos, inicio_cena = [], 0.0
            for c in cenas:
                if c.get("audio_do_video"):
                    trechos.append(f"between(t,{inicio_cena:.3f},{inicio_cena + c['duracao_segundos']:.3f})")
                inicio_cena += c["duracao_segundos"]
            fundo_usado = som_fundo
            if trechos:
                fundo_usado = pasta / "som_fundo_mudo_nas_cenas.wav"
                r = subprocess.run([caminho_ffmpeg(), "-y", "-i", str(som_fundo), "-af", f"volume=enable='{'+'.join(trechos)}':volume=0", str(fundo_usado)], capture_output=True, text=True)
                if r.returncode != 0:
                    raise RuntimeError(f"FFmpeg falhou ao silenciar o som de fundo: {r.stderr[-800:]}")
            render.mixar_audio_com_fundo(com_pausas, fundo_usado, final, VOLUME_SOM_DE_FUNDO)
            if fundo_usado != som_fundo:
                fundo_usado.unlink(missing_ok=True)
        else:
            r = subprocess.run([caminho_ffmpeg(), "-y", "-i", str(com_pausas), "-c:a", "aac", "-b:a", "192k", str(final)], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"FFmpeg falhou ao gerar o áudio final:\n{r.stderr[-1500:]}")
        com_pausas.unlink(missing_ok=True)
        audio_path = final

    metadados.update(cenas=cenas, audio_natural=natural_audio, audio_arquivo=audio_path.name, aprovado=False)
    caminho_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- legenda (tempos deslocados) + vídeos ---
    from types import SimpleNamespace
    submaker = SimpleNamespace(cues=_cues_ajustados(pasta, metadados))
    roteiro = (pasta / "roteiro.txt").read_text(encoding="utf-8")
    config = metadados.get("legenda") or {}
    formatos_ativos = _formatos_de(metadados.get("formatos", "ambos"))
    nomes = {}
    for k, (formato, estilo) in enumerate(formatos_ativos.items()):
        sufixo = formato.replace(":", "x")
        avisar(f"Remontando o vídeo ({formato})", 30 + 60 * k / len(formatos_ativos))
        legenda_path = None
        if config.get("modo") != "nenhuma" and submaker.cues:  # vídeo em branco: ainda não há fala
            legenda_path = subtitles.gerar_ass(submaker, pasta / f"legenda_{sufixo}.ass", roteiro=roteiro, config=config, **estilo)
        imagens = [(pasta / f"cena{i:02d}_{sufixo}.png", c["duracao_segundos"]) for i, c in enumerate(cenas)]
        with _trava_do_video(slug):
            saida = pasta / f"video_{sufixo}.mp4"
            render.renderizar_slideshow(imagens, audio_path, legenda_path, formato, saida, transicao=metadados.get("transicao", "fade"))
        nomes[formato] = saida.name
    avisar("Pronto", 100)
    return {"video_16_9": nomes.get("16:9"), "video_9_16": nomes.get("9:16")}


def _peca_com_audio_do_video(video: Path, destino: Path) -> dict:
    """Uma cena cujo som é o do próprio vídeo da Base (ex.: uma introdução feita no Photoshop, com música). O
    áudio entra na narração no lugar da fala; se o vídeo não tiver som, a cena fica em silêncio."""
    import subprocess

    from engine.ferramentas import caminho_ffmpeg

    duracao = biblioteca.duracao_de(video)
    if duracao <= 0.2:
        raise RuntimeError("Não consegui ler a duração desse vídeo.")
    r = subprocess.run([caminho_ffmpeg(), "-y", "-i", str(video), "-vn", "-af", "apad", "-t", f"{duracao:.3f}", "-ar", "44100", "-ac", "2", str(destino)], capture_output=True, text=True)
    if r.returncode != 0 or not destino.exists():  # vídeo sem trilha de áudio
        r = subprocess.run([caminho_ffmpeg(), "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{duracao:.3f}", str(destino)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"FFmpeg falhou ao pegar o áudio do vídeo:\n{r.stderr[-800:]}")
    return {"texto": "", "arquivo": destino, "dur": tts.duracao_do_audio(destino), "cues": [], "substitui": None, "audio_do_video": True}


@_com_trava_de_edicao
def editar_estrutura(
    slug: str, operacao: str, indice: int | None = None, posicao: int | None = None, texto: str = "",
    descricao_imagem: str = "", midia_tipo: str = "", midia_nome: str = "", edicoes: dict | None = None,
    progresso: Callable[[str, float], None] | None = None, audio_do_video: bool = False,
    ajustar_ao_video: bool = False,
) -> dict:
    """Muda a estrutura do vídeo SEM regenerar tudo: "adicionar" uma cena (narração nova + imagem/vídeo),
    "remover" uma (com a fala dela) ou "substituir" o texto de várias (só elas são narradas de novo; as outras
    falas, imagens e vídeos ficam iguais). O áudio natural é remontado na nova ordem, as imagens são
    renumeradas, o roteiro passa a ter um parágrafo por cena e no fim tempos/legenda/vídeos são refeitos."""
    import subprocess

    from engine.ferramentas import caminho_ffmpeg

    def avisar(etapa: str, pct: float) -> None:
        if progresso is not None:
            progresso(etapa, pct)

    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        raise RuntimeError("Vídeo não encontrado.")
    m = json.loads(caminho_meta.read_text(encoding="utf-8"))
    if m.get("publicado"):
        raise RuntimeError("Esse vídeo já foi publicado.")
    if m.get("sem_narracao") or m.get("narracao_customizada"):
        raise RuntimeError("Só dá pra editar cenas em vídeo com narração por IA (com áudio seu, o texto precisa continuar igual ao áudio).")
    cenas = m.get("cenas") or []
    narracao = pasta / (m.get("narracao_arquivo") or "narracao.mp3")
    if not cenas or not narracao.exists() or not (pasta / "cues.json").exists():
        raise RuntimeError('Esse vídeo foi gerado antes dessa edição existir — use "Regenerar" uma vez para habilitar.')

    naturais = [c.get("duracao_natural", c["duracao_segundos"]) for c in cenas]
    inicios = [0.0]
    for n in naturais:
        inicios.append(inicios[-1] + n)
    ordem = list(range(len(cenas)))  # >= 0: cena antiga; < 0: peça nova (-1 = novos[0], -2 = novos[1]...)
    novos: list = []                 # peças narradas agora: {"texto","arquivo","dur","cues","substitui"}
    idioma, voz = m.get("idioma", "pt-BR"), m.get("voz", "mulher")

    def narrar(txt: str, k: int) -> dict:
        arquivo = pasta / f"_nova_{k}.mp3"
        sm = tts.sintetizar(txt, idioma, voz, arquivo)
        return {"texto": txt, "arquivo": arquivo, "dur": tts.duracao_do_audio(arquivo),
                "cues": [(c.start.total_seconds(), c.end.total_seconds(), c.content) for c in sm.cues], "substitui": None}

    if operacao == "remover":
        if indice is None or not (0 <= indice < len(cenas)) or len(cenas) < 2:
            raise RuntimeError("Cena inexistente ou única (o vídeo precisa de pelo menos uma cena).")
        ordem.remove(indice)
    elif operacao == "adicionar":
        if audio_do_video:
            video_da_cena = biblioteca.caminho_video_valido(midia_nome) if midia_tipo == "video" else None
            if not video_da_cena:
                raise RuntimeError("Escolha um vídeo da Base para usar o áudio dele.")
            avisar("Pegando o áudio do vídeo", 8)
            novos.append(_peca_com_audio_do_video(video_da_cena, pasta / "_nova_0.wav"))
        else:
            if len(texto.strip()) < 3:
                raise RuntimeError("Escreva o texto que será narrado nessa cena.")
            avisar("Narrando a cena nova", 8)
            novos.append(narrar(texto.strip(), 0))
            video_maior = biblioteca.caminho_video_valido(midia_nome) if midia_tipo == "video" else None
            if ajustar_ao_video and video_maior and biblioteca.duracao_de(video_maior) > novos[0]["dur"] + 0.2:
                # o vídeo é mais longo que a fala: a cena dura o vídeo todo (a fala termina e o resto é pausa)
                novos[0]["dur_cena"] = biblioteca.duracao_de(video_maior)
        ordem.insert(len(cenas) if posicao is None else max(0, min(int(posicao), len(cenas))), -1)
    elif operacao == "substituir":
        pedidos = {int(k): str(v).strip() for k, v in (edicoes or {}).items()}
        if not pedidos or any(not (0 <= i < len(cenas)) or len(t) < 3 for i, t in pedidos.items()):
            raise RuntimeError("Edição inválida (cena inexistente ou texto vazio).")
        if any(cenas[i].get("audio_do_video") for i in pedidos):
            raise RuntimeError("Essa cena usa o áudio do próprio vídeo: não tem texto para editar.")
        for n, (i, txt) in enumerate(sorted(pedidos.items())):
            avisar(f"Narrando o texto novo ({n + 1}/{len(pedidos)})", 8 + 14 * n / len(pedidos))
            peca = narrar(txt, n)
            peca["substitui"] = i
            novos.append(peca)
            ordem[i] = -(n + 1)
    else:
        raise RuntimeError("Operação inválida.")

    # --- narração natural remontada na nova ordem ---
    avisar("Remontando a narração", 24)
    entradas = ["-i", str(narracao)]
    for peca in novos:
        entradas += ["-i", str(peca["arquivo"])]
    filtros = []
    for k, i in enumerate(ordem):
        if i < 0:
            fonte, corte = f"[{-i}:a]", ""
        else:
            fonte = "[0:a]"
            corte = f"atrim=start={inicios[i]:.3f}" + (f":end={inicios[i + 1]:.3f}" if i < len(cenas) - 1 else "") + ","
        filtros.append(f"{fonte}{corte}asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo[p{k}]")
    filtros.append("".join(f"[p{k}]" for k in range(len(ordem))) + f"concat=n={len(ordem)}:v=0:a=1[saida]")
    # o arquivo de saída nunca pode ser o de entrada (o ffmpeg não edita no lugar): alterna entre dois nomes
    nova_narracao = pasta / ("narracao_editada_b.mp3" if narracao.name == "narracao_editada.mp3" else "narracao_editada.mp3")
    r = subprocess.run(
        [caminho_ffmpeg(), "-y", *entradas, "-filter_complex", ";".join(filtros), "-map", "[saida]", "-c:a", "libmp3lame", "-q:a", "3", str(nova_narracao)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ao remontar a narração:\n{r.stderr[-1500:]}")

    # --- cues (tempos das palavras) na nova ordem ---
    antigos = json.loads((pasta / "cues.json").read_text(encoding="utf-8"))
    novos_cues, deslocamento = [], 0.0
    for i in ordem:
        if i < 0:
            peca = novos[-i - 1]
            novos_cues += [{"start": s + deslocamento, "end": e + deslocamento, "content": c} for s, e, c in peca["cues"]]
            deslocamento += peca["dur"]
        else:
            ini, fim = inicios[i], inicios[i + 1]
            novos_cues += [
                {"start": c["start"] - ini + deslocamento, "end": c["end"] - ini + deslocamento, "content": c["content"]}
                for c in antigos if ini - 1e-6 <= c["start"] < fim - 1e-6 or (i == len(cenas) - 1 and c["start"] >= ini - 1e-6)
            ]
            deslocamento += naturais[i]
    (pasta / "cues.json").write_text(json.dumps(novos_cues, ensure_ascii=False), encoding="utf-8")

    # --- arquivos de imagem/vídeo das cenas renumerados (a cena substituída leva os dela junto) ---
    avisar("Reorganizando as imagens", 40)
    formatos_ativos = _formatos_de(m.get("formatos", "ambos"))
    temporarios = {}
    for k_antigo in range(len(cenas)):
        for suf in ("16x9", "9x16"):
            for ext in (".png", ".mp4", ".fonte"):
                origem = pasta / f"cena{k_antigo:02d}_{suf}{ext}"
                if origem.exists():
                    tmp = pasta / f"_mover_{k_antigo:02d}_{suf}{ext}"
                    origem.rename(tmp)
                    temporarios[(k_antigo, suf, ext)] = tmp
    mapa_indices = {}
    for k_novo, i in enumerate(ordem):
        antigo = i if i >= 0 else novos[-i - 1]["substitui"]
        if antigo is None:
            continue
        mapa_indices[antigo] = k_novo
        for (k_antigo, suf, ext), tmp in list(temporarios.items()):
            if k_antigo == antigo:
                tmp.rename(pasta / f"cena{k_novo:02d}_{suf}{ext}")
                del temporarios[(k_antigo, suf, ext)]
    for tmp in temporarios.values():  # o que sobrou é da cena removida
        tmp.unlink(missing_ok=True)

    def remapear(mapa: dict | None) -> dict:
        return {str(mapa_indices[int(k)]): v for k, v in (mapa or {}).items() if int(k) in mapa_indices}

    imagens_base = remapear(m.get("imagens_base_cenas"))
    videos_base = remapear(m.get("videos_base_cenas"))
    descricoes = remapear(m.get("descricoes_cenas"))
    plano_visual = remapear(m.get("plano_visual"))

    # --- imagem/vídeo da cena nova (só em "adicionar") ---
    if operacao == "adicionar":
        k_nova = ordem.index(-1)
        dur_nova = novos[0]["dur"]
        titulo = m.get("titulo", slug)
        for k, (formato, estilo) in enumerate(formatos_ativos.items()):
            suf = formato.replace(":", "x")
            avisar(f"Preparando a imagem da cena nova ({formato})", 46 + 20 * k / len(formatos_ativos))
            png = pasta / f"cena{k_nova:02d}_{suf}.png"
            if midia_tipo == "video" and biblioteca.caminho_video_valido(midia_nome):
                render.preparar_clip(biblioteca.caminho_video_valido(midia_nome), estilo["largura"], estilo["altura"], png.with_suffix(".mp4"), png, max_segundos=int(novos[0].get("dur_cena", dur_nova)) + (2 if audio_do_video or "dur_cena" in novos[0] else 5))
            elif midia_tipo == "imagem" and biblioteca.caminho_imagem_valida(midia_nome):
                visuals._cobrir(Image.open(biblioteca.caminho_imagem_valida(midia_nome)).convert("RGB"), estilo["largura"], estilo["altura"]).save(png, "PNG")
            else:
                try:
                    visuals.gerar_fundo(m.get("estilo_imagem", "procedural"), estilo["largura"], estilo["altura"], png, cena=descricao_imagem.strip() or texto, estilo_extra=m.get("descricao_video", ""), contexto=titulo, duracao=novos[0].get("dur_cena", dur_nova))
                except RuntimeError:
                    visuals.gerar_fundo_procedural(estilo["largura"], estilo["altura"], png, semente=texto)
        if "16:9" not in formatos_ativos:
            _derivar_16x9_do_vertical(pasta, k_nova)
        if midia_tipo == "video" and biblioteca.caminho_video_valido(midia_nome):
            videos_base[str(k_nova)] = midia_nome
        elif midia_tipo == "imagem" and biblioteca.caminho_imagem_valida(midia_nome):
            imagens_base[str(k_nova)] = midia_nome
        elif descricao_imagem.strip():
            descricoes[str(k_nova)] = descricao_imagem.strip()[:300]

    # --- metadados e roteiro (um parágrafo por cena) ---
    novas_cenas = []
    for i in ordem:
        if i < 0:
            peca = novos[-i - 1]
            cena_nova = {"texto": peca["texto"], "duracao_segundos": round(peca.get("dur_cena", peca["dur"]), 3), "duracao_natural": round(peca["dur"], 3)}
            if peca.get("audio_do_video"):
                cena_nova["audio_do_video"] = True  # duração fixa: é a do vídeo, com o som dele
            novas_cenas.append(cena_nova)
        else:
            novas_cenas.append(cenas[i])
    (pasta / "roteiro.txt").write_text("\n\n".join(c["texto"] for c in novas_cenas if c["texto"]), encoding="utf-8")
    m.update(
        cenas=novas_cenas, narracao_arquivo=nova_narracao.name, num_cenas=len(novas_cenas),
        imagens_base_cenas=imagens_base, videos_base_cenas=videos_base, descricoes_cenas=descricoes, plano_visual=plano_visual, aprovado=False,
    )
    caminho_meta.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    for peca in novos:
        peca["arquivo"].unlink(missing_ok=True)
    if narracao.name.startswith("narracao_editada") and narracao != nova_narracao:
        narracao.unlink(missing_ok=True)  # a versão anterior da narração editada

    return aplicar_duracoes(slug, {}, progresso=lambda etapa, pct: avisar(etapa, 70 + 0.3 * pct))


@_com_trava_de_edicao
def regenerar_legenda(slug: str, config: dict, progresso: Callable[[str, float], None] | None = None) -> dict:
    """Refaz só a legenda (estilo, tamanho, posição, cor...) e remonta os vídeos,
    sem mexer em roteiro, narração nem imagens. Precisa de cues.json (salvo em
    vídeos gerados/regenerados depois desse recurso)."""
    from datetime import timedelta
    from types import SimpleNamespace

    def avisar(etapa: str, percentual: float) -> None:
        if progresso is not None:
            progresso(etapa, percentual)

    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        raise RuntimeError("Vídeo não encontrado.")
    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    if metadados.get("sem_narracao"):
        raise RuntimeError("Vídeo sem narração não tem legenda.")
    cues_arquivo = pasta / "cues.json"
    roteiro_arquivo = pasta / "roteiro.txt"
    if not cues_arquivo.exists() or not roteiro_arquivo.exists():
        raise RuntimeError('Esse vídeo foi gerado antes da legenda ser editável — clique em "Regenerar" uma vez pra habilitar.')
    audio_nome = metadados.get("audio_arquivo")
    audio_path = pasta / audio_nome if audio_nome else None
    if audio_path is None or not audio_path.exists() or not metadados.get("cenas"):
        raise RuntimeError("Faltam arquivos originais — regenere o vídeo inteiro uma vez.")

    submaker = SimpleNamespace(cues=_cues_ajustados(pasta, metadados))
    roteiro = roteiro_arquivo.read_text(encoding="utf-8")
    formatos_ativos = _formatos_de(metadados.get("formatos", "ambos"))
    nomes_video = {}
    passo = 0
    for formato, estilo in formatos_ativos.items():
        sufixo = formato.replace(":", "x")
        avisar(f"Refazendo a legenda ({formato})", 10 + 80 * passo / len(formatos_ativos))
        legenda_path = None
        if config.get("modo") != "nenhuma":
            legenda_path = subtitles.gerar_ass(submaker, pasta / f"legenda_{sufixo}.ass", roteiro=roteiro, config=config, **estilo)
        imagens = [(pasta / f"cena{i:02d}_{sufixo}.png", c["duracao_segundos"]) for i, c in enumerate(metadados["cenas"])]
        if not all(p.exists() for p, _ in imagens):
            raise RuntimeError("Imagem de alguma cena sumiu do disco — regenere o vídeo inteiro uma vez.")
        avisar(f"Remontando o vídeo ({formato})", 10 + 80 * (passo + 0.5) / len(formatos_ativos))
        with _trava_do_video(slug):
            caminho_video = pasta / f"video_{sufixo}.mp4"
            render.renderizar_slideshow(imagens, audio_path, legenda_path, formato, caminho_video, transicao=metadados.get("transicao", "fade"))
        nomes_video[formato] = caminho_video.name
        passo += 1
    _salvar_metadados(pasta, legenda=config, aprovado=False)
    avisar("Pronto", 100)
    return {"video_16_9": nomes_video.get("16:9"), "video_9_16": nomes_video.get("9:16")}


def regenerar_cena(slug: str, indice: int, progresso: Callable[[str, float], None] | None = None, imagem_propria: Path | None = None, video_proprio: Path | None = None) -> dict:
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
    # se você descreveu a imagem que quer pra essa cena, a descrição vale no lugar do texto da narração
    texto_cena = (metadados.get("descricoes_cenas") or {}).get(str(indice)) or cenas[indice]["texto"]
    # sem descrição sua, vale o plano visual que o roteiro gerou para essa cena (com a descrição sua, ela manda)
    plano_da_cena = None if (metadados.get("descricoes_cenas") or {}).get(str(indice)) else (metadados.get("plano_visual") or {}).get(str(indice))

    formatos_ativos = _formatos_de(metadados.get("formatos", "ambos"))
    total_passos = len(formatos_ativos) * 2  # gerar imagem + remontar, por formato
    passo = 0
    thumbnail_atualizada = False
    nomes_video = {}

    for formato, estilo in formatos_ativos.items():
        sufixo = formato.replace(":", "x")
        caminho_imagem = pasta / f"cena{indice:02d}_{sufixo}.png"

        passo += 1
        avisar(f"{'Aplicando sua imagem' if imagem_propria else 'Gerando nova imagem'} da cena ({formato})", 10 + 80 * passo / total_passos)
        clip_cena = pasta / f"cena{indice:02d}_{sufixo}.mp4"
        if video_proprio:
            avisar(f"Preparando o vídeo da cena ({formato})", 10 + 80 * passo / total_passos)
            render.preparar_clip(video_proprio, estilo["largura"], estilo["altura"], clip_cena, caminho_imagem)
        else:
            clip_cena.unlink(missing_ok=True)  # a cena volta a ser imagem
        if video_proprio:
            pass
        elif imagem_propria:
            # imagem enviada por você: só recorta pro formato (sem distorcer), sem chamar a IA
            visuals._cobrir(Image.open(imagem_propria).convert("RGB"), estilo["largura"], estilo["altura"]).save(caminho_imagem, "PNG")
        else:
            try:
                visuals.gerar_fundo(
                    estilo_imagem, estilo["largura"], estilo["altura"], caminho_imagem,
                    cena=texto_cena, estilo_extra=descricao_video, contexto=metadados.get("titulo", slug),
                    duracao=(cenas[indice].get("duracao_segundos", 0) if indice < len(cenas) else 0),
                    plano=plano_da_cena,
                )
            except RuntimeError as erro:
                print(f"[aviso] cena {indice} ({estilo_imagem}) falhou, usando procedural: {erro}")
                visuals.gerar_fundo_procedural(estilo["largura"], estilo["altura"], caminho_imagem, semente=f"{texto_cena}-{passo}")

        passo += 1
        avisar(f"Remontando o vídeo ({formato})", 10 + 80 * passo / total_passos)
        with _trava_do_video(slug):
            # lê as imagens só depois de pegar a vez: inclui as trocas que outras cenas terminaram nesse meio-tempo
            imagens_com_duracao = []
            for i, cena in enumerate(cenas):
                img = pasta / f"cena{i:02d}_{sufixo}.png"
                if not img.exists():
                    raise RuntimeError(f"Imagem da cena {i} sumiu do disco — regenere o vídeo inteiro uma vez.")
                imagens_com_duracao.append((img, cena["duracao_segundos"]))

            legenda_path = pasta / f"legenda_{sufixo}.ass"
            legenda_path = legenda_path if (not sem_narracao and legenda_path.exists()) else None

            caminho_video = pasta / f"video_{sufixo}.mp4"
            render.renderizar_slideshow(imagens_com_duracao, audio_path, legenda_path, formato, caminho_video, transicao=metadados.get("transicao", "fade"))
            nomes_video[formato] = caminho_video.name

    if "16:9" not in formatos_ativos:
        _derivar_16x9_do_vertical(pasta, indice)

    if indice == 0:
        avisar("Atualizando a thumbnail", 95)
        texto_thumb = metadados.get("thumbnail_texto") or metadados.get("titulo", slug)
        cor_thumb = thumbnail_mod.cor_de_hex(metadados.get("thumbnail_cor", ""))
        posicao_thumb = metadados.get("thumbnail_posicao", "baixo-centro")
        px_thumb = metadados.get("thumbnail_tamanho_px")
        tamanho_thumb = int(px_thumb) if isinstance(px_thumb, (int, float)) and px_thumb else thumbnail_mod.TAMANHOS.get(metadados.get("thumbnail_tamanho", "medio"), 80)
        pos_x_thumb, pos_y_thumb = metadados.get("thumbnail_pos_x"), metadados.get("thumbnail_pos_y")
        pos_livre_thumb = (pos_x_thumb, pos_y_thumb) if isinstance(pos_x_thumb, (int, float)) and isinstance(pos_y_thumb, (int, float)) else None
        # se a base da thumbnail foi trocada manualmente (imagem custom ou
        # outra cena), usa ela; senão continua sendo a cena 0 que acabou de
        # ser regenerada
        fonte_txt = pasta / "thumbnail_fonte.txt"
        base_thumb = pasta / fonte_txt.read_text(encoding="utf-8").strip() if fonte_txt.exists() else pasta / "cena00_16x9.png"
        if not base_thumb.exists():
            base_thumb = pasta / "cena00_16x9.png"
        thumbnail_mod.gerar_thumbnail(base_thumb, texto_thumb, pasta / "thumbnail.png", cor_thumb, posicao_thumb, tamanho_thumb, pos_livre_thumb)
        thumbnail_atualizada = True

    if imagem_propria:
        imagem_propria.unlink(missing_ok=True)
    _salvar_metadados(pasta, aprovado=False)
    avisar("Pronto", 100)
    return {
        "video_16_9": nomes_video.get("16:9"),
        "video_9_16": nomes_video.get("9:16"),
        "thumbnail_atualizada": thumbnail_atualizada,
    }
