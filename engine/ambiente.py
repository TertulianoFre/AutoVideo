"""Som de fundo (chuva, música suave) — sintetizado localmente, sem internet,
sem custo. Usado tanto no vídeo sem narração (som de fundo é o áudio inteiro,
ex: 30 min de chuva pra relaxar) quanto misturado bem baixo por baixo da
narração num vídeo normal."""

import wave
from pathlib import Path

import numpy as np

TIPOS_SUPORTADOS = ["chuva", "musica"]


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


def gerar_musica_suave(duracao_segundos: float, caminho_wav: Path, taxa_amostragem: int = 32000) -> Path:
    """Um acorde suave e sustentado (tipo pad ambiente), com um swell de volume
    bem lento — não é uma composição de verdade, só um fundo tranquilo."""
    rng = np.random.default_rng()
    n = max(1, int(duracao_segundos * taxa_amostragem))
    t = np.linspace(0, duracao_segundos, n, dtype=np.float32)

    frequencias = [110.00, 130.81, 164.81, 196.00]  # A2-C3-E3-G3, acorde suave
    sinal = np.zeros(n, dtype=np.float32)
    for freq in frequencias:
        fase = rng.uniform(0, 2 * np.pi)
        sinal += np.sin(2 * np.pi * freq * t + fase) / len(frequencias)

    # "respiração" de volume bem lenta, pra não soar um tom morto/contínuo
    swell = 0.55 + 0.45 * np.sin(2 * np.pi * t / 23 + rng.uniform(0, 6))
    sinal *= swell

    pico = np.max(np.abs(sinal)) or 1.0
    sinal = sinal / pico * 0.5
    amostras = (sinal * 32767).astype(np.int16)

    caminho_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(caminho_wav), "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(taxa_amostragem)
        wav.writeframes(amostras.tobytes())

    return caminho_wav


def gerar_som_ambiente(tipo: str, duracao_segundos: float, caminho_wav: Path, descricao: str = "") -> Path:
    """descricao: pedido livre do usuário (ex: "som de floresta"). Hoje ainda
    não sintetiza qualquer coisa descrita — só direciona pro tipo mais
    parecido (chuva ou música); é um espaço pra crescer depois."""
    if tipo == "musica":
        return gerar_musica_suave(duracao_segundos, caminho_wav)
    return gerar_som_chuva(duracao_segundos, caminho_wav)
