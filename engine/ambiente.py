"""Som de fundo (chuva, música suave...) — sintetizado localmente, sem
internet, sem custo. Usado tanto no vídeo sem narração (som de fundo é o
áudio inteiro, ex: 30 min de chuva pra relaxar) quanto misturado bem baixo
por baixo da narração num vídeo normal."""

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


# ---------------------------------------------------------------------------
# sinais-base (cada um devolve o array de amostras, sem salvar em disco —
# assim dá pra combinar mais de um antes de gravar o wav final)
# ---------------------------------------------------------------------------

def _sinal_chuva(duracao_segundos: float, taxa_amostragem: int, rng: np.random.Generator) -> np.ndarray:
    n = max(1, int(duracao_segundos * taxa_amostragem))
    ruido = rng.normal(0, 1, n).astype(np.float32)

    # filtro passa-baixa simples (média móvel) — tira o chiado mais agudo e
    # deixa o ruído branco com uma textura mais parecida com chuva.
    filtrado = _filtro_media_movel(ruido, 5)

    # modulação de amplitude bem lenta e suave, só pra não soar "morto"/robótico
    t = np.linspace(0, duracao_segundos, n, dtype=np.float32)
    modulacao = 0.85 + 0.15 * np.sin(2 * np.pi * t / 37)
    return filtrado * modulacao


def _sinal_oceano(duracao_segundos: float, taxa_amostragem: int, rng: np.random.Generator) -> np.ndarray:
    """Ondas quebrando: ruído filtrado (mais grave que a chuva) com um "swell"
    assimétrico — sobe devagar, quebra rápido — no ritmo de uma onda real."""
    n = max(1, int(duracao_segundos * taxa_amostragem))
    ruido = rng.normal(0, 1, n).astype(np.float32)

    # janela maior que a chuva = som mais grave/abafado, tipo água, não chiado
    filtrado = _filtro_media_movel(ruido, 25)

    t = np.linspace(0, duracao_segundos, n, dtype=np.float32)
    periodo_onda = 9.0
    fase = (t % periodo_onda) / periodo_onda
    # sobe em curva suave (sin) e quebra rápido (queda ao quadrado) — assimétrico de propósito
    envelope = np.where(fase < 0.65, np.sin(fase / 0.65 * np.pi / 2), (1 - (fase - 0.65) / 0.35) ** 2)
    return filtrado * (0.35 + 0.65 * envelope)


def _sinal_fogueira(duracao_segundos: float, taxa_amostragem: int, rng: np.random.Generator) -> np.ndarray:
    """Fogueira: um chiado grave e constante de fundo (a brasa) + estalos
    aleatórios (pops curtos com decaimento rápido) por cima, no timing de
    lenha estalando."""
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

    return fundo + estalos * 0.5


def _sinal_vento(duracao_segundos: float, taxa_amostragem: int, rng: np.random.Generator) -> np.ndarray:
    """Vento: ruído com filtro passa-faixa aproximado (diferença de duas médias
    móveis) pra dar um "uivo" em vez do chiado plano da chuva, com rajadas
    irregulares (soma de senos em períodos diferentes, não sincronizados)."""
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
    return filtrado * rajada


def _sinal_musica(duracao_segundos: float, taxa_amostragem: int, rng: np.random.Generator) -> np.ndarray:
    """Um acorde suave e sustentado (tipo pad ambiente), com um swell de volume
    bem lento — não é uma composição de verdade, só um fundo tranquilo."""
    n = max(1, int(duracao_segundos * taxa_amostragem))
    t = np.linspace(0, duracao_segundos, n, dtype=np.float32)

    frequencias = [110.00, 130.81, 164.81, 196.00]  # A2-C3-E3-G3, acorde suave
    sinal = np.zeros(n, dtype=np.float32)
    for freq in frequencias:
        fase = rng.uniform(0, 2 * np.pi)
        sinal += np.sin(2 * np.pi * freq * t + fase) / len(frequencias)

    # "respiração" de volume bem lenta, pra não soar um tom morto/contínuo
    swell = 0.55 + 0.45 * np.sin(2 * np.pi * t / 23 + rng.uniform(0, 6))
    return sinal * swell


_SINAIS_BASE = {
    "chuva": (_sinal_chuva, 0.6),
    "musica": (_sinal_musica, 0.5),
    "oceano": (_sinal_oceano, 0.6),
    "fogueira": (_sinal_fogueira, 0.55),
    "vento": (_sinal_vento, 0.55),
}


def gerar_som_chuva(duracao_segundos: float, caminho_wav: Path, taxa_amostragem: int = 32000) -> Path:
    return _salvar_wav(_sinal_chuva(duracao_segundos, taxa_amostragem, np.random.default_rng()), caminho_wav, taxa_amostragem, 0.6)


def gerar_som_oceano(duracao_segundos: float, caminho_wav: Path, taxa_amostragem: int = 32000) -> Path:
    return _salvar_wav(_sinal_oceano(duracao_segundos, taxa_amostragem, np.random.default_rng()), caminho_wav, taxa_amostragem, 0.6)


def gerar_som_fogueira(duracao_segundos: float, caminho_wav: Path, taxa_amostragem: int = 32000) -> Path:
    return _salvar_wav(_sinal_fogueira(duracao_segundos, taxa_amostragem, np.random.default_rng()), caminho_wav, taxa_amostragem, 0.55)


def gerar_som_vento(duracao_segundos: float, caminho_wav: Path, taxa_amostragem: int = 32000) -> Path:
    return _salvar_wav(_sinal_vento(duracao_segundos, taxa_amostragem, np.random.default_rng()), caminho_wav, taxa_amostragem, 0.55)


def gerar_musica_suave(duracao_segundos: float, caminho_wav: Path, taxa_amostragem: int = 32000) -> Path:
    return _salvar_wav(_sinal_musica(duracao_segundos, taxa_amostragem, np.random.default_rng()), caminho_wav, taxa_amostragem, 0.5)


# ---------------------------------------------------------------------------
# "camadas": eventos extra que dá pra somar por cima de um som-base quando a
# descrição livre ("outro") menciona palavras-chave específicas — não é
# sintetizar qualquer coisa, mas combina em vez de só escolher 1 dos 5 tipos.
# ---------------------------------------------------------------------------

def _camada_passaros(duracao_segundos: float, taxa_amostragem: int, rng: np.random.Generator) -> np.ndarray:
    """Chilrear de pássaros: bursts curtos de tom com glide de frequência
    (sobe/desce), espalhados em intervalos aleatórios e esparsos."""
    n = max(1, int(duracao_segundos * taxa_amostragem))
    camada = np.zeros(n, dtype=np.float32)
    n_chilros = max(1, int(duracao_segundos * 0.4))
    duracao_chilro = max(1, int(0.15 * taxa_amostragem))
    for _ in range(n_chilros):
        inicio = rng.integers(0, max(1, n - duracao_chilro))
        freq_inicio = rng.uniform(2200, 4200)
        freq_fim = freq_inicio + rng.uniform(-900, 900)
        freq_instantanea = np.linspace(freq_inicio, freq_fim, duracao_chilro).astype(np.float32)
        fase = np.cumsum(2 * np.pi * freq_instantanea / taxa_amostragem)
        tom = np.sin(fase).astype(np.float32)
        envelope = (np.sin(np.linspace(0, np.pi, duracao_chilro)).astype(np.float32)) ** 2
        camada[inicio:inicio + duracao_chilro] += tom * envelope * rng.uniform(0.3, 0.6)
    return camada


def _camada_trovao(duracao_segundos: float, taxa_amostragem: int, rng: np.random.Generator) -> np.ndarray:
    """Trovão: estrondos graves e esparsos — ruído bem filtrado (grave) com
    decaimento longo, tipo bombo."""
    n = max(1, int(duracao_segundos * taxa_amostragem))
    camada = np.zeros(n, dtype=np.float32)
    n_trovoes = max(1, int(duracao_segundos / 18))
    for _ in range(n_trovoes):
        duracao_trovao = max(1, int(rng.uniform(1.5, 3.0) * taxa_amostragem))
        inicio = rng.integers(0, max(1, n - duracao_trovao))
        ruido = rng.normal(0, 1, duracao_trovao).astype(np.float32)
        grave = _filtro_media_movel(ruido, 80)
        decaimento = np.exp(-np.linspace(0, 3.5, duracao_trovao)).astype(np.float32)
        subida = np.clip(np.linspace(0, 1, max(1, int(0.15 * taxa_amostragem))), 0, 1)
        envelope = decaimento.copy()
        envelope[:len(subida)] *= subida
        camada[inicio:inicio + duracao_trovao] += grave * envelope * rng.uniform(0.6, 1.0)
    return camada


def _camada_multidao(duracao_segundos: float, taxa_amostragem: int, rng: np.random.Generator) -> np.ndarray:
    """Multidão/cafeteria: murmúrio — várias faixas de ruído passa-faixa em
    médias frequências, moduladas e defasadas entre si, simulando um monte de
    vozes baixas e indistintas ao fundo."""
    n = max(1, int(duracao_segundos * taxa_amostragem))
    soma = np.zeros(n, dtype=np.float32)
    t = np.linspace(0, duracao_segundos, n, dtype=np.float32)
    for _ in range(5):
        ruido = rng.normal(0, 1, n).astype(np.float32)
        estreito = _filtro_media_movel(ruido, int(rng.integers(6, 14)))
        largo = _filtro_media_movel(ruido, int(rng.integers(40, 70)))
        faixa = estreito - largo
        modulacao = 0.7 + 0.3 * np.sin(2 * np.pi * t / rng.uniform(3, 7) + rng.uniform(0, 6))
        soma += faixa * modulacao
    return soma / 5


_CAMADA_GERADORES = {
    "passaros": (_camada_passaros, 0.5),
    "trovao": (_camada_trovao, 0.6),
    "multidao": (_camada_multidao, 0.45),
}

_PALAVRAS_CHAVE_POR_TIPO = {
    "oceano": ["oceano", "mar", "praia", "onda", "ondas", "água do mar"],
    "fogueira": ["fogueira", "fogo", "lareira", "lenha", "crepitar", "estalar"],
    "vento": ["vento", "ventania", "brisa", "ventos", "tempestade de vento"],
    "musica": ["música", "musica", "piano", "melodia", "instrumental", "pad"],
}

_PALAVRAS_CHAVE_POR_CAMADA = {
    "passaros": ["pássaro", "passaro", "pássaros", "passaros", "passarinho", "passarinhos", "aves", "canto de pássaro", "canto de passaro"],
    "trovao": ["trovão", "trovao", "trovões", "trovoes", "tempestade", "relâmpago", "relampago"],
    "multidao": ["multidão", "multidao", "cafeteria", "restaurante", "café", "cafe", "bar", "conversando", "pessoas falando"],
}


def _tipo_base_mais_parecido(descricao: str) -> str:
    descricao_lower = descricao.lower()
    for tipo, palavras in _PALAVRAS_CHAVE_POR_TIPO.items():
        if any(palavra in descricao_lower for palavra in palavras):
            return tipo
    return "chuva"


def _camadas_detectadas(descricao: str) -> list:
    descricao_lower = descricao.lower()
    return [camada for camada, palavras in _PALAVRAS_CHAVE_POR_CAMADA.items() if any(p in descricao_lower for p in palavras)]


def gerar_som_ambiente(tipo: str, duracao_segundos: float, caminho_wav: Path, descricao: str = "", taxa_amostragem: int = 32000) -> Path:
    """tipo em TIPOS_SUPORTADOS: sintetiza direto. tipo "outro" (com descricao
    livre, ex: "floresta com pássaros", "tempestade com trovão", "cafeteria
    movimentada"): escolhe o tipo-base real mais parecido e SOMA por cima
    qualquer camada extra reconhecida na descrição (pássaros/trovão/multidão)
    — ainda não sintetiza qualquer coisa descrita, mas combina em vez de só
    escolher 1 dos 5 tipos fixos."""
    rng = np.random.default_rng()

    if tipo in _SINAIS_BASE:
        gerador_base, pico = _SINAIS_BASE[tipo]
        sinal = gerador_base(duracao_segundos, taxa_amostragem, rng)
        return _salvar_wav(sinal, caminho_wav, taxa_amostragem, pico)

    tipo_base = _tipo_base_mais_parecido(descricao)
    gerador_base, pico = _SINAIS_BASE[tipo_base]
    sinal = gerador_base(duracao_segundos, taxa_amostragem, rng)

    for camada in _camadas_detectadas(descricao):
        gerador_camada, peso = _CAMADA_GERADORES[camada]
        sinal = sinal + gerador_camada(duracao_segundos, taxa_amostragem, rng) * peso

    return _salvar_wav(sinal, caminho_wav, taxa_amostragem, pico)
