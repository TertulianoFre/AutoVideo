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


def preparar_clip(origem: Path, largura: int, altura: int, saida_mp4: Path, saida_png: Path, max_segundos: int = 60) -> None:
    """Deixa um vídeo da Base no tamanho exato do formato (corta o excesso, sem esticar), sem áudio
    (a narração é o áudio do vídeo final), e tira o primeiro quadro como imagem da cena. O clip
    é repetido em loop na montagem se a cena for mais longa que ele."""
    filtro = f"scale={largura}:{altura}:force_original_aspect_ratio=increase,crop={largura}:{altura},fps=30,setsar=1,format=yuv420p"
    comando = [
        caminho_ffmpeg(), "-y", "-i", str(origem), "-t", str(max_segundos), "-vf", filtro,
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", str(saida_mp4),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0 or not saida_mp4.exists():
        raise RuntimeError(f"FFmpeg falhou ao preparar o vídeo da cena:\n{resultado.stderr[-1500:]}")
    quadro = subprocess.run([caminho_ffmpeg(), "-y", "-i", str(saida_mp4), "-frames:v", "1", str(saida_png)], capture_output=True, text=True)
    if quadro.returncode != 0 or not saida_png.exists():
        raise RuntimeError("Não consegui tirar o primeiro quadro do vídeo da cena.")


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


TRANSICOES = {
    "nenhuma": None,
    "fade": "fade",
    "dissolver": "dissolve",
    "deslizar": "smoothleft",
    "zoom": "fade",      # opções antigas (muito fortes) viram fade
    "circulo": "fade",
    "aleatoria": "aleatoria",
}
_SORTEIO_TRANSICOES = ["fade", "dissolve", "smoothleft", "smoothright", "fadeblack"]  # só as suaves
DURACAO_TRANSICAO = 0.5


def renderizar_slideshow(
    imagens_com_duracao: list,
    audio: Path,
    legenda: Path | None,
    formato: str,
    saida: Path,
    transicao: str = "fade",
) -> Path:
    """imagens_com_duracao: lista de (caminho_da_imagem, duração_em_segundos),
    uma por cena, na ordem em que aparecem no vídeo. legenda=None pra vídeo sem
    legenda (ex: modo ambiente, que não tem narração)."""
    largura, altura = FORMATOS[formato]

    n = len(imagens_com_duracao)
    tipo = TRANSICOES.get(transicao, "fade")
    duracoes = [max(d, 0.1) for _, d in imagens_com_duracao]
    # a transição sobrepõe o fim de uma cena com o começo da próxima; pra o vídeo
    # não encurtar, cada cena (menos a última) ganha a duração da transição a mais
    t = min(DURACAO_TRANSICAO, 0.35 * min(duracoes)) if (tipo and n > 1) else 0.0
    usar_transicao = tipo is not None and n > 1 and t >= 0.12

    comando = [caminho_ffmpeg(), "-y"]
    for i, (imagem, _) in enumerate(imagens_com_duracao):
        extra = t if (usar_transicao and i < n - 1) else 0.0
        clip = Path(imagem).with_suffix(".mp4")
        if clip.exists():  # cena com vídeo (importado da Base): repete em loop até cobrir a cena
            comando += ["-stream_loop", "-1", "-t", f"{duracoes[i] + extra:.3f}", "-i", str(clip)]
        else:
            comando += ["-loop", "1", "-framerate", "30", "-t", f"{duracoes[i] + extra:.3f}", "-i", str(imagem)]
    comando += ["-i", str(audio)]

    trechos_filtro = []
    labels = []
    for i in range(n):
        trechos_filtro.append(f"[{i}:v]scale={largura}:{altura},setsar=1,fps=30,format=yuv420p[v{i}]")
        labels.append(f"[v{i}]")
    if usar_transicao:
        import random
        anterior, acumulado = "[v0]", 0.0
        for i in range(1, n):
            acumulado += duracoes[i - 1]
            efeito = random.choice(_SORTEIO_TRANSICOES) if tipo == "aleatoria" else tipo
            saida_label = "[vcat]" if i == n - 1 else f"[x{i}]"
            trechos_filtro.append(f"{anterior}[v{i}]xfade=transition={efeito}:duration={t:.3f}:offset={acumulado:.3f}{saida_label}")
            anterior = saida_label
    else:
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
