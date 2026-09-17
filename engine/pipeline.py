"""Orquestra o pipeline completo: roteiro -> narração -> cenas -> imagens -> legenda -> vídeo final.

Também tem o modo "ambiente" (gerar_video_ambiente): som contínuo (ex: chuva) +
imagem, sem narração nem legenda, pra vídeos longos de relaxar/dormir."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from engine import ambiente, canal, render, roteiro as roteiro_mod, scenes, subtitles, tts, visuals
from engine.roteiro import PALAVRAS_POR_MINUTO

RAIZ_SAIDA = Path(__file__).resolve().parent.parent / "output"

# Ajustes de legenda por formato: no Shorts (9:16) a tela é mais estreita,
# então usamos fonte menor e a legenda mais perto da borda inferior, pra
# sobrar mais espaço de imagem visível.
ESTILO_LEGENDA_POR_FORMATO = {
    "16:9": {"largura": 1920, "altura": 1080, "fontsize": 82, "marginv": 55, "palavras_por_legenda": 6},
    "9:16": {"largura": 1080, "altura": 1920, "fontsize": 62, "marginv": 130, "palavras_por_legenda": 5},
}

# Vídeo ambiente: uma imagem nova a cada tantos segundos — bem calmo, não
# precisa (nem deve) trocar como se fosse uma cena narrada.
SEGUNDOS_POR_IMAGEM_AMBIENTE = 240


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
    progresso: Callable[[str, float], None] | None = None,
) -> ResultadoGeracao:
    def avisar(etapa: str, percentual: float) -> None:
        if progresso is not None:
            progresso(etapa, percentual)

    pasta = RAIZ_SAIDA / _slug(titulo)
    pasta.mkdir(parents=True, exist_ok=True)
    _salvar_metadados(pasta, titulo=titulo, data_postagem=data_postagem, descricao_video=descricao_video, modo="narrado")

    if roteiro is None:
        avisar("Escrevendo o roteiro", 3)
        # o contexto do canal é sempre levado em conta aqui, como base — não
        # precisa repetir isso na descrição de cada vídeo.
        roteiro = roteiro_mod.gerar_roteiro(
            titulo,
            duracao_alvo_minutos or 1.0,
            contexto_canal=canal.obter_contexto(),
            descricao_video=descricao_video,
        )
        print(f"[roteiro gerado]\n{roteiro}\n")
        (pasta / "roteiro.txt").write_text(roteiro, encoding="utf-8")

    avisar("Gerando a narração", 8)
    audio_path = pasta / "narracao.mp3"
    submaker = tts.sintetizar(roteiro, idioma, voz, audio_path)

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

    avisar("Dividindo o roteiro em cenas", 18)
    cenas = scenes.dividir_em_cenas(submaker, roteiro)

    # imagens de todas as cenas, nos dois formatos, são a etapa mais demorada
    # (sobretudo com foto/ia, que dependem de internet) — vão de 20% a 85%.
    total_imagens = len(cenas) * len(ESTILO_LEGENDA_POR_FORMATO)
    imagens_feitas = 0

    videos = {}
    for formato, estilo in ESTILO_LEGENDA_POR_FORMATO.items():
        sufixo = formato.replace(":", "x")
        legenda_path = subtitles.gerar_ass(submaker, pasta / f"legenda_{sufixo}.ass", roteiro=roteiro, **estilo)

        imagens_com_duracao = []
        for i, cena in enumerate(cenas):
            caminho_imagem = pasta / f"cena{i:02d}_{sufixo}.png"
            try:
                visuals.gerar_fundo(
                    estilo_imagem,
                    estilo["largura"],
                    estilo["altura"],
                    caminho_imagem,
                    cena=cena.texto,
                    estilo_extra=descricao_video,
                )
            except RuntimeError as erro:
                # Fonte externa (foto/ia) falhou (rede, serviço fora do ar) — não
                # trava o vídeo inteiro por causa de uma cena, usa o procedural.
                print(f"[aviso] cena {i} ({estilo_imagem}) falhou, usando procedural: {erro}")
                visuals.gerar_fundo_procedural(estilo["largura"], estilo["altura"], caminho_imagem, semente=cena.texto)
            imagens_com_duracao.append((caminho_imagem, cena.duracao_segundos))

            imagens_feitas += 1
            avisar(f"Gerando imagens ({formato})", 20 + 65 * imagens_feitas / total_imagens)

        avisar(f"Montando o vídeo ({formato})", 88 if formato == "16:9" else 94)
        videos[formato] = render.renderizar_slideshow(
            imagens_com_duracao, audio_path, legenda_path, formato, pasta / f"video_{sufixo}.mp4"
        )

    avisar("Pronto", 100)
    return ResultadoGeracao(pasta, audio_path, videos["16:9"], videos["9:16"], duracao_real, roteiro, tags)


def gerar_video_ambiente(
    titulo: str,
    duracao_alvo_minutos: float = 15.0,
    tipo_som: str = "chuva",
    estilo_imagem: str = "procedural",
    descricao_video: str = "",
    data_postagem: str | None = None,
    progresso: Callable[[str, float], None] | None = None,
) -> ResultadoGeracao:
    """Vídeo sem narração: som ambiente em loop (ex: chuva) + imagem que troca
    bem devagar. Pra vídeos longos (15-60 min) de relaxar/dormir/estudar."""

    def avisar(etapa: str, percentual: float) -> None:
        if progresso is not None:
            progresso(etapa, percentual)

    pasta = RAIZ_SAIDA / _slug(titulo)
    pasta.mkdir(parents=True, exist_ok=True)
    _salvar_metadados(
        pasta, titulo=titulo, data_postagem=data_postagem, descricao_video=descricao_video, modo="ambiente", tipo_som=tipo_som
    )

    duracao_segundos = duracao_alvo_minutos * 60

    avisar(f"Gerando o som ambiente ({tipo_som})", 10)
    audio_path = pasta / "ambiente.wav"
    ambiente.gerar_som_ambiente(tipo_som, duracao_segundos, audio_path)

    n_imagens = max(1, round(duracao_segundos / SEGUNDOS_POR_IMAGEM_AMBIENTE))
    duracao_por_imagem = duracao_segundos / n_imagens
    contexto_cena = f"{titulo}. {descricao_video}".strip(". ") or titulo

    videos = {}
    formatos = list(ESTILO_LEGENDA_POR_FORMATO.items())
    for indice_formato, (formato, estilo) in enumerate(formatos):
        sufixo = formato.replace(":", "x")

        imagens_com_duracao = []
        for i in range(n_imagens):
            caminho_imagem = pasta / f"ambiente{i:02d}_{sufixo}.png"
            try:
                visuals.gerar_fundo(
                    estilo_imagem,
                    estilo["largura"],
                    estilo["altura"],
                    caminho_imagem,
                    cena=contexto_cena,
                    estilo_extra=descricao_video,
                )
            except RuntimeError as erro:
                print(f"[aviso] imagem {i} ({estilo_imagem}) falhou, usando procedural: {erro}")
                visuals.gerar_fundo_procedural(estilo["largura"], estilo["altura"], caminho_imagem, semente=contexto_cena)
            imagens_com_duracao.append((caminho_imagem, duracao_por_imagem))

            progresso_imagens = (indice_formato * n_imagens + i + 1) / (len(formatos) * n_imagens)
            avisar(f"Gerando imagens ({formato})", 20 + 60 * progresso_imagens)

        avisar(f"Montando o vídeo ({formato})", 88 if formato == "16:9" else 94)
        videos[formato] = render.renderizar_slideshow(
            imagens_com_duracao, audio_path, None, formato, pasta / f"video_{sufixo}.mp4"
        )

    avisar("Pronto", 100)
    return ResultadoGeracao(pasta, audio_path, videos["16:9"], videos["9:16"], duracao_segundos, "", [])
