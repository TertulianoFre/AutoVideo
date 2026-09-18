"""Som de fundo (chuva, música suave) — sintetizado localmente, sem internet,
sem custo. Usado tanto no vídeo sem narração (som de fundo é o áudio inteiro,
ex: 30 min de chuva pra relaxar) quanto misturado bem baixo por baixo da
narração num vídeo normal."""

import wave
from pathlib import Path

import numpy as np

TIPOS_SUPORTADOS = ["chuva", "musica", "oceano", "fogueira", "vento"]


def _filtro_media_movel(sinal: np.ndarray, janela: int) -> np.ndarray:
    kernel = np.ones(janela, dtype=np.float32) / janela
    return np.convolve(sinal, kernel, mode="same")


def _salvar_wav(sinal: np.ndarray, caminho_wav: Path, taxa_amostragem: int, pico_alvo: float = 0.6) -> Path:
    pico = np.max(np.abs(sinal)) or 1.0
    sinal = sinal / pico * pico_alvo
    amostras = (sinal * 32767).astype(np.int16)

    caminho_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(caminho_wav), "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(taxa_amostragem)
        wav.writeframes(amostras.tobytes())
    return caminho_wav


def gerar_som_chuva(duracao_segundos: float, caminho_wav: Path, taxa_amostragem: int = 32000) -> Path:
    rng = np.random.default_rng()
    n = max(1, int(duracao_segundos * taxa_amostragem))
    ruido = rng.normal(0, 1, n).astype(np.float32)

    # filtro passa-baixa simples (média móvel) — tira o chiado mais agudo e
    # deixa o ruído branco com uma textura mais parecida com chuva.
    filtrado = _filtro_media_movel(ruido, 5)

    # modulação de amplitude bem lenta e suave, só pra não soar "morto"/robótico
    t = np.linspace(0, duracao_segundos, n, dtype=np.float32)
    modulacao = 0.85 + 0.15 * np.sin(2 * np.pi * t / 37)
    sinal = filtrado * modulacao

    return _salvar_wav(sinal, caminho_wav, taxa_amostragem, 0.6)


def gerar_som_oceano(duracao_segundos: float, caminho_wav: Path, taxa_amostragem: int = 32000) -> Path:
    """Ondas quebrando: ruído filtrado (mais grave que a chuva) com um "swell"
    assimétrico — sobe devagar, quebra rápido — no ritmo de uma onda real."""
    rng = np.random.default_rng()
    n = max(1, int(duracao_segundos * taxa_amostragem))
    ruido = rng.normal(0, 1, n).astype(np.float32)

    # janela maior que a chuva = som mais grave/abafado, tipo água, não chiado
    filtrado = _filtro_media_movel(ruido, 25)

    t = np.linspace(0, duracao_segundos, n, dtype=np.float32)
    periodo_onda = 9.0
    fase = (t % periodo_onda) / periodo_onda
    # sobe em curva suave (sin) e quebra rápido (queda ao quadrado) — assimétrico de propósito
    envelope = np.where(fase < 0.65, np.sin(fase / 0.65 * np.pi / 2), (1 - (fase - 0.65) / 0.35) ** 2)
    sinal = filtrado * (0.35 + 0.65 * envelope)

    return _salvar_wav(sinal, caminho_wav, taxa_amostragem, 0.6)


def gerar_som_fogueira(duracao_segundos: float, caminho_wav: Path, taxa_amostragem: int = 32000) -> Path:
    """Fogueira: um chiado grave e constante de fundo (a brasa) + estalos
    aleatórios (pops curtos com decaimento rápido) por cima, no timing de
    lenha estalando."""
    rng = np.random.default_rng()
    n = max(1, int(duracao_segundos * taxa_amostragem))

    ruido = rng.normal(0, 1, n).astype(np.float32)
    fundo = _filtro_media_movel(ruido, 40) * 0.5  # bem abafado, só textura de fundo

    # estalos: eventos aleatórios espalhados ao longo da duração, cada um um
    # estouro curto de ruído agudo com decaimento exponencial rápido
    estalos = np.zeros(n, dtype=np.float32)
    n_estalos = int(duracao_segundos * 2.2)  # ritmo médio de ~2 estalos por segundo
    duracao_estalo = int(0.06 * taxa_amostragem)
    for _ in range(n_estalos):
        inicio = rng.integers(0, max(1, n - duracao_estalo))
        pico_estalo = rng.uniform(0.4, 1.0)
        decaimento = np.exp(-np.linspace(0, 12, duracao_estalo)).astype(np.float32)
        ruido_estalo = rng.normal(0, 1, duracao_estalo).astype(np.float32)
        estalos[inicio:inicio + duracao_estalo] += ruido_estalo * decaimento * pico_estalo

    sinal = fundo + estalos * 0.5
    return _salvar_wav(sinal, caminho_wav, taxa_amostragem, 0.55)


def gerar_som_vento(duracao_segundos: float, caminho_wav: Path, taxa_amostragem: int = 32000) -> Path:
    """Vento: ruído com filtro passa-faixa aproximado (diferença de duas médias
    móveis) pra dar um "uivo" em vez do chiado plano da chuva, com rajadas
    irregulares (soma de senos em períodos diferentes, não sincronizados)."""
    rng = np.random.default_rng()
    n = max(1, int(duracao_segundos * taxa_amostragem))
    ruido = rng.normal(0, 1, n).astype(np.float32)

    # passa-faixa aproximado: tira o grave (média larga) do meio-agudo (média estreita)
    suave = _filtro_media_movel(ruido, 9)
    largo = _filtro_media_movel(ruido, 60)
    filtrado = suave - largo

    t = np.linspace(0, duracao_segundos, n, dtype=np.float32)
    rajada = (
        0.6
        + 0.25 * np.sin(2 * np.pi * t / 13 + rng.uniform(0, 6))
        + 0.15 * np.sin(2 * np.pi * t / 4.3 + rng.uniform(0, 6))
    )
    sinal = filtrado * rajada

    return _salvar_wav(sinal, caminho_wav, taxa_amostragem, 0.55)


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

    return _salvar_wav(sinal, caminho_wav, taxa_amostragem, 0.5)


_GERADORES = {
    "chuva": gerar_som_chuva,
    "musica": gerar_musica_suave,
    "oceano": gerar_som_oceano,
    "fogueira": gerar_som_fogueira,
    "vento": gerar_som_vento,
}

# pra quando o tipo é "outro" com descrição livre: casa por palavra-chave com
# o som real mais parecido, em vez de sempre cair pra chuva sem nem olhar o
# que a pessoa pediu.
_PALAVRAS_CHAVE_POR_TIPO = {
    "oceano": ["oceano", "mar", "praia", "onda", "ondas", "água do mar"],
    "fogueira": ["fogueira", "fogo", "lareira", "lenha", "crepitar", "estalar"],
    "vento": ["vento", "ventania", "brisa", "ventos", "tempestade de vento"],
    "musica": ["música", "musica", "piano", "melodia", "instrumental", "pad"],
}


def _tipo_mais_parecido(descricao: str) -> str:
    descricao_lower = descricao.lower()
    for tipo, palavras in _PALAVRAS_CHAVE_POR_TIPO.items():
        if any(palavra in descricao_lower for palavra in palavras):
            return tipo
    return "chuva"


def gerar_som_ambiente(tipo: str, duracao_segundos: float, caminho_wav: Path, descricao: str = "") -> Path:
    """tipo "outro" (com descricao livre, ex: "som de floresta com pássaros"):
    ainda não sintetiza qualquer coisa descrita — casa por palavra-chave com o
    som real mais parecido entre os sintetizados (chuva/música/oceano/fogueira
    /vento); sem palavra-chave reconhecida, cai pra chuva."""
    gerador = _GERADORES.get(tipo) or _GERADORES[_tipo_mais_parecido(descricao)]
    return gerador(duracao_segundos, caminho_wav)
