"""Localiza o executável do FFmpeg sem depender do PATH do processo que chamou
o motor (o backend web, por exemplo, pode rodar com um PATH diferente do
terminal onde ele foi instalado)."""

import functools
import os
import shutil
from pathlib import Path


@functools.lru_cache(maxsize=1)
def caminho_ffmpeg() -> str:
    encontrado = shutil.which("ffmpeg")
    if encontrado:
        return encontrado

    # instalado via winget (Gyan.FFmpeg.Essentials) — procura na pasta padrão
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if base.exists():
        candidatos = sorted(base.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"))
        if candidatos:
            return str(candidatos[0])

    raise RuntimeError(
        "Não encontrei o ffmpeg.exe. Confirme que ele está instalado "
        "(winget install Gyan.FFmpeg.Essentials) e tente de novo."
    )
