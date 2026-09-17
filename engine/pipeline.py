"""Orquestra o pipeline completo: roteiro -> narração -> cenas -> imagens -> legenda -> vídeo final."""

import re
from dataclasses import dataclass
from pathlib import Path

from engine import render, roteiro as roteiro_mod, scenes, subtitles, tts, visuals
from engine.roteiro import PALAVRAS_POR_MINUTO

RAIZ_SAIDA = Path(__file__).resolve().parent.parent / "output"

# Ajustes de legenda por formato: no Shorts (9:16) a tela é mais estreita,
# então usamos fonte menor e a legenda mais perto da borda inferior, pra
# sobrar mais espaço de imagem visível.
ESTILO_LEGENDA_POR_FORMATO = {
    "16:9": {"largura": 1920, "altura": 1080, "fontsize": 82, "marginv": 55, "palavras_por_legenda": 6},
    "9:16": {"largura": 1080, "altura": 1920, "fontsize": 62, "marginv": 130, "palavras_por_legenda": 5},
}


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


def gerar_video(
    titulo: str,
    roteiro: str | None = None,
    idioma: str = "pt-BR",
    voz: str = "mulher",
    estilo_imagem: str = "procedural",
    duracao_alvo_minutos: float | None = None,
) -> ResultadoGeracao:
    pasta = RAIZ_SAIDA / _slug(titulo)
    pasta.mkdir(parents=True, exist_ok=True)

    if roteiro is None:
        roteiro = roteiro_mod.gerar_roteiro(titulo, duracao_alvo_minutos or 1.0)
        print(f"[roteiro gerado]\n{roteiro}\n")
        (pasta / "roteiro.txt").write_text(roteiro, encoding="utf-8")

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

    cenas = scenes.dividir_em_cenas(submaker, roteiro)

    videos = {}
    for formato, estilo in ESTILO_LEGENDA_POR_FORMATO.items():
        sufixo = formato.replace(":", "x")
        legenda_path = subtitles.gerar_ass(submaker, pasta / f"legenda_{sufixo}.ass", roteiro=roteiro, **estilo)

        imagens_com_duracao = []
        for i, cena in enumerate(cenas):
            caminho_imagem = pasta / f"cena{i:02d}_{sufixo}.png"
            try:
                visuals.gerar_fundo(
                    estilo_imagem, estilo["largura"], estilo["altura"], caminho_imagem, cena=cena.texto
                )
            except RuntimeError as erro:
                # Fonte externa (foto/ia) falhou (rede, serviço fora do ar) — não
                # trava o vídeo inteiro por causa de uma cena, usa o procedural.
                print(f"[aviso] cena {i} ({estilo_imagem}) falhou, usando procedural: {erro}")
                visuals.gerar_fundo_procedural(estilo["largura"], estilo["altura"], caminho_imagem, semente=cena.texto)
            imagens_com_duracao.append((caminho_imagem, cena.duracao_segundos))

        videos[formato] = render.renderizar_slideshow(
            imagens_com_duracao, audio_path, legenda_path, formato, pasta / f"video_{sufixo}.mp4"
        )

    return ResultadoGeracao(pasta, audio_path, videos["16:9"], videos["9:16"], duracao_real, roteiro)
