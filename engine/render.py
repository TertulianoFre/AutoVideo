"""Monta o vídeo final com FFmpeg: imagens de cada cena (slideshow) + narração +
legenda queimada."""

import subprocess
from pathlib import Path

from engine.ferramentas import caminho_ffmpeg

FORMATOS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
}


def _legenda_para_filtro(caminho_legenda: Path) -> str:
    # No filtro subtitles do ffmpeg, ':' e '\' no caminho precisam ser escapados.
    escapado = str(caminho_legenda).replace("\\", "/").replace(":", "\\:")
    return f"subtitles='{escapado}'"


def mixar_audio_com_fundo(audio_principal: Path, som_fundo: Path, saida: Path, volume_fundo: float = 0.2) -> Path:
    """Mistura o som de fundo (chuva, música...) bem baixo por baixo do áudio
    principal (narração). O fundo repete em loop se for mais curto."""
    comando = [
        caminho_ffmpeg(), "-y",
        "-i", str(audio_principal),
        "-stream_loop", "-1", "-i", str(som_fundo),
        "-filter_complex",
        f"[1:a]volume={volume_fundo}[fundo];[0:a][fundo]amix=inputs=2:duration=first:dropout_transition=0[aout]",
        "-map", "[aout]",
        "-c:a", "aac", "-b:a", "192k",
        str(saida),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ao misturar o som de fundo:\n{resultado.stderr[-2000:]}")
    return saida


def renderizar_slideshow(
    imagens_com_duracao: list,
    audio: Path,
    legenda: Path | None,
    formato: str,
    saida: Path,
) -> Path:
    """imagens_com_duracao: lista de (caminho_da_imagem, duração_em_segundos),
    uma por cena, na ordem em que aparecem no vídeo. legenda=None pra vídeo sem
    legenda (ex: modo ambiente, que não tem narração)."""
    largura, altura = FORMATOS[formato]

    comando = [caminho_ffmpeg(), "-y"]
    for imagem, duracao in imagens_com_duracao:
        comando += ["-loop", "1", "-t", f"{max(duracao, 0.1):.3f}", "-i", str(imagem)]
    comando += ["-i", str(audio)]

    n = len(imagens_com_duracao)
    trechos_filtro = []
    labels = []
    for i in range(n):
        trechos_filtro.append(f"[{i}:v]scale={largura}:{altura},setsar=1,format=yuv420p[v{i}]")
        labels.append(f"[v{i}]")
    trechos_filtro.append(f"{''.join(labels)}concat=n={n}:v=1:a=0[vcat]")
    if legenda is not None:
        trechos_filtro.append(f"[vcat]{_legenda_para_filtro(legenda)}[vout]")
    else:
        trechos_filtro.append("[vcat]null[vout]")
    filtro = ";".join(trechos_filtro)

    comando += [
        "-filter_complex", filtro,
        "-map", "[vout]", "-map", f"{n}:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(saida),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ao renderizar slideshow {formato}:\n{resultado.stderr[-2000:]}")
    return saida
