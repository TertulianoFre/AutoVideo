"""Gera o roteiro automaticamente a partir de um título, usando a API de texto
gratuita da Pollinations.ai (compatível com o formato da OpenAI, sem chave)."""

import time

import requests

POLLINATIONS_CHAT_URL = "https://text.pollinations.ai/openai"

# Ritmo médio de fala do edge-tts nas vozes usadas aqui — usado tanto pra pedir
# o roteiro do tamanho certo quanto pro aviso de duração em pipeline.py.
PALAVRAS_POR_MINUTO = 150

PROMPT_SISTEMA = (
    "Você escreve roteiros curtos em português do Brasil para narração em vídeo. "
    "Escreva só o texto corrido a ser lido em voz alta, sem títulos, sem marcações, "
    'sem introdução tipo "neste vídeo" ou "olá pessoal" — vá direto ao assunto. '
    "Frases curtas e claras, fáceis de narrar em voz alta. Respeite rigorosamente "
    "a contagem de palavras pedida."
)


def gerar_roteiro(titulo: str, duracao_alvo_minutos: float = 1.0, tentativas: int = 3) -> str:
    palavras_alvo = round(duracao_alvo_minutos * PALAVRAS_POR_MINUTO)
    mensagem_usuario = f"Escreva um roteiro de aproximadamente {palavras_alvo} palavras sobre: {titulo}"

    payload = {
        "model": "openai",
        "messages": [
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": mensagem_usuario},
        ],
    }

    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            resposta = requests.post(POLLINATIONS_CHAT_URL, json=payload, timeout=60)
            if resposta.ok:
                dados = resposta.json()
                texto = dados["choices"][0]["message"]["content"].strip()
                if texto:
                    return texto
            ultimo_erro = f"HTTP {resposta.status_code}"
        except (requests.RequestException, KeyError, ValueError, IndexError) as erro:
            ultimo_erro = str(erro)
        time.sleep(2 * tentativa)

    raise RuntimeError(f"Geração de roteiro falhou {tentativas}x ({ultimo_erro}) pro título: {titulo}")
