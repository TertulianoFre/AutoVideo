"""Narração via edge-tts: sintetiza o áudio e captura o tempo de cada palavra."""

import asyncio
from pathlib import Path

import edge_tts

VOZES = {
    "pt-BR": {
        "mulher": "pt-BR-FranciscaNeural",
        "homem": "pt-BR-AntonioNeural",
        "crianca": "pt-BR-FranciscaNeural",
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
}


def resolver_voz(idioma: str, voz: str) -> tuple[str, str]:
    vozes_do_idioma = VOZES.get(idioma, VOZES["pt-BR"])
    voice_id = vozes_do_idioma.get(voz, vozes_do_idioma["mulher"])
    pitch = PITCH_POR_VOZ.get(voz, "+0Hz")
    return voice_id, pitch


async def _sintetizar_async(texto: str, idioma: str, voz: str, audio_path: Path) -> edge_tts.SubMaker:
    voice_id, pitch = resolver_voz(idioma, voz)
    comunicador = edge_tts.Communicate(texto, voice_id, pitch=pitch, boundary="WordBoundary")
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
