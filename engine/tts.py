"""Narração via edge-tts: sintetiza o áudio e captura o tempo de cada palavra.
Também dá suporte a narração gravada por você (upload) — nesse caso não há
timestamp real por palavra, então aproxima um ritmo constante."""

import asyncio
import subprocess
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import edge_tts

from engine.ferramentas import caminho_ffprobe

VOZES = {
    "pt-BR": {
        "mulher": "pt-BR-FranciscaNeural",
        "homem": "pt-BR-AntonioNeural",
        "crianca": "pt-BR-FranciscaNeural",
        "mulher_animada": "pt-BR-ThalitaMultilingualNeural",
        "homem_animado": "pt-BR-AntonioNeural",
    },
    "en-US": {
        "mulher": "en-US-AvaNeural",
        "homem": "en-US-AndrewNeural",
        "crianca": "en-US-AvaNeural",
    },
    "es-ES": {
        "mulher": "es-ES-ElviraNeural",
        "homem": "es-ES-AlvaroNeural",
        "crianca": "es-ES-ElviraNeural",
    },
    "fr-FR": {
        "mulher": "fr-FR-DeniseNeural",
        "homem": "fr-FR-HenriNeural",
        "crianca": "fr-FR-DeniseNeural",
    },
}

# Não existe voz infantil nessas vozes neurais gratuitas: "criança" é uma
# aproximação, usando a voz feminina com o tom (pitch) elevado.
PITCH_POR_VOZ = {
    "mulher": "+0Hz",
    "homem": "+0Hz",
    "crianca": "+35Hz",
    "mulher_animada": "+6Hz",
    "homem_animado": "+4Hz",
}

# Vozes "animadas": a neural multilíngue (Thalita) é a mais expressiva em português; junto com ritmo
# um pouco mais rápido e tom mais alto dá a entonação empolgada de vídeo de curiosidades.
RITMO_POR_VOZ = {
    "mulher_animada": "+12%",
    "homem_animado": "+10%",
}


def resolver_voz(idioma: str, voz: str) -> tuple[str, str, str]:
    vozes_do_idioma = VOZES.get(idioma, VOZES["pt-BR"])
    voice_id = vozes_do_idioma.get(voz) or vozes_do_idioma["homem" if voz == "homem_animado" else "mulher"]
    return voice_id, PITCH_POR_VOZ.get(voz, "+0Hz"), RITMO_POR_VOZ.get(voz, "+0%")


async def _sintetizar_async(texto: str, idioma: str, voz: str, audio_path: Path) -> edge_tts.SubMaker:
    voice_id, pitch, ritmo = resolver_voz(idioma, voz)
    comunicador = edge_tts.Communicate(texto, voice_id, rate=ritmo, pitch=pitch, boundary="WordBoundary")
    submaker = edge_tts.SubMaker()

    with open(audio_path, "wb") as arquivo_audio:
        async for chunk in comunicador.stream():
            if chunk["type"] == "audio":
                arquivo_audio.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)

    return submaker


def sintetizar(texto: str, idioma: str, voz: str, audio_path: Path) -> edge_tts.SubMaker:
    """Gera o áudio da narração e devolve as marcações de tempo de cada palavra."""
    return asyncio.run(_sintetizar_async(texto, idioma, voz, audio_path))


def salvar_narracao_customizada(conteudo: bytes, destino: Path) -> Path:
    """Valida (reencodando com ffmpeg, mesmo padrão usado na Base) e salva um
    áudio de narração gravado/enviado por você, no lugar da síntese por TTS."""
    import tempfile

    from engine.ferramentas import caminho_ffmpeg

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
        tmp.write(conteudo)
        caminho_tmp = Path(tmp.name)
    try:
        comando = [caminho_ffmpeg(), "-y", "-i", str(caminho_tmp), "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(destino)]
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.returncode != 0 or not destino.exists():
            destino.unlink(missing_ok=True)
            raise ValueError("não consegui reconhecer esse arquivo como áudio válido")
    finally:
        caminho_tmp.unlink(missing_ok=True)
    return destino


def duracao_do_audio(audio_path: Path) -> float:
    comando = [
        caminho_ffprobe(), "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0 or not resultado.stdout.strip():
        raise RuntimeError(f"Não consegui ler a duração desse áudio:\n{resultado.stderr[-500:]}")
    return float(resultado.stdout.strip())


@dataclass
class _CuePseudo:
    start: timedelta
    end: timedelta
    content: str = ""


@dataclass
class _SubMakerPseudo:
    cues: list = field(default_factory=list)


def submaker_aproximado(roteiro: str, duracao_segundos: float) -> _SubMakerPseudo:
    """'Submaker' falso pra narração gravada por você: sem timestamp real por
    palavra (o TTS local é quem gera isso), então distribui a duração total do
    áudio igualmente entre as palavras do roteiro. É uma aproximação — assume
    ritmo de fala constante, sem pausas maiores em vírgulas/parágrafos — mas
    mantém cenas e legendas funcionando com o mesmo código de sempre."""
    palavras = roteiro.split()
    if not palavras:
        return _SubMakerPseudo([])

    duracao_por_palavra = duracao_segundos / len(palavras)
    cues = []
    t = 0.0
    for palavra in palavras:
        inicio = timedelta(seconds=t)
        t += duracao_por_palavra
        cues.append(_CuePseudo(inicio, timedelta(seconds=t), palavra))
    return _SubMakerPseudo(cues)
