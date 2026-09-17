"""Modo de vídeo ambiente: som contínuo (chuva) + imagem, sem narração nem
legenda. Pensado pra vídeos longos (ex: 15-30 min de chuva pra relaxar/dormir).

O som de chuva é sintetizado localmente (ruído filtrado) — não é uma gravação
real, mas é grátis, automático e não depende de internet."""

import wave
from pathlib import Path

import numpy as np

TIPOS_SUPORTADOS = ["chuva"]


def gerar_som_chuva(duracao_segundos: float, caminho_wav: Path, taxa_amostragem: int = 32000) -> Path:
    rng = np.random.default_rng()
    n = max(1, int(duracao_segundos * taxa_amostragem))
    ruido = rng.normal(0, 1, n).astype(np.float32)

    # filtro passa-baixa simples (média móvel) — tira o chiado mais agudo e
    # deixa o ruído branco com uma textura mais parecida com chuva.
    janela = 5
    kernel = np.ones(janela, dtype=np.float32) / janela
    filtrado = np.convolve(ruido, kernel, mode="same")

    # modulação de amplitude bem lenta e suave, só pra não soar "morto"/robótico
    t = np.linspace(0, duracao_segundos, n, dtype=np.float32)
    modulacao = 0.85 + 0.15 * np.sin(2 * np.pi * t / 37)
    sinal = filtrado * modulacao

    pico = np.max(np.abs(sinal)) or 1.0
    sinal = sinal / pico * 0.6
    amostras = (sinal * 32767).astype(np.int16)

    caminho_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(caminho_wav), "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(taxa_amostragem)
        wav.writeframes(amostras.tobytes())

    return caminho_wav


def gerar_som_ambiente(tipo: str, duracao_segundos: float, caminho_wav: Path) -> Path:
    if tipo == "chuva":
        return gerar_som_chuva(duracao_segundos, caminho_wav)
    raise ValueError(f"Tipo de som ambiente não suportado: '{tipo}' (disponíveis: {TIPOS_SUPORTADOS})")
