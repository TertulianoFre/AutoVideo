"""Gera o roteiro e as hashtags automaticamente a partir de um título, usando a
API de texto gratuita da Pollinations.ai (compatível com o formato da OpenAI,
sem chave)."""

import time

import requests

POLLINATIONS_CHAT_URL = "https://text.pollinations.ai/openai"

# Ritmo médio de fala do edge-tts nas vozes usadas aqui — usado tanto pra pedir
# o roteiro do tamanho certo quanto pro aviso de duração em pipeline.py.
PALAVRAS_POR_MINUTO = 150

PROMPT_SISTEMA = (
    "Você escreve roteiros bem elaborados, em português do Brasil, para narração em vídeo. "
    "Estrutura: abra com um gancho que prenda a atenção (uma pergunta intrigante ou um fato "
    "surpreendente), desenvolva com 2-3 detalhes concretos e interessantes sobre o assunto "
    "(fatos, números, comparações — nada genérico ou vago), e feche com uma frase de impacto. "
    "Escreva só o texto corrido a ser lido em voz alta, sem títulos, sem marcações, "
    'sem introdução tipo "neste vídeo" ou "olá pessoal" — vá direto pro gancho. '
    "Frases curtas e claras, fáceis de narrar em voz alta. Respeite rigorosamente "
    "a contagem de palavras pedida."
)


def _chamar_pollinations(mensagens: list, tentativas: int = 4) -> str:
    # reasoning_effort baixo: esse modelo às vezes gasta todo o orçamento de
    # tokens "pensando" e não sobra espaço pra escrever a resposta final.
    payload = {"model": "openai", "messages": mensagens, "reasoning_effort": "low"}
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            resposta = requests.post(POLLINATIONS_CHAT_URL, json=payload, timeout=60)
            if resposta.ok:
                dados = resposta.json()
                escolhas = dados.get("choices") or []
                texto = (escolhas[0].get("message", {}).get("content", "") if escolhas else "").strip()
                if texto:
                    return texto
                ultimo_erro = f"resposta sem conteúdo: {str(dados)[:200]}"
            else:
                ultimo_erro = f"HTTP {resposta.status_code}: {resposta.text[:200]}"
        except (requests.RequestException, ValueError) as erro:
            ultimo_erro = str(erro)
        time.sleep(2 * tentativa)
    raise RuntimeError(f"Chamada à Pollinations falhou {tentativas}x ({ultimo_erro})")


def gerar_roteiro(
    titulo: str,
    duracao_alvo_minutos: float = 1.0,
    contexto_canal: str = "",
    descricao_video: str = "",
    tentativas: int = 3,
) -> str:
    palavras_alvo = round(duracao_alvo_minutos * PALAVRAS_POR_MINUTO)

    partes = [f"Escreva um roteiro de aproximadamente {palavras_alvo} palavras sobre: {titulo}"]
    if contexto_canal:
        partes.append(f"Contexto do canal (nicho, tom, público — mantenha o roteiro alinhado com isso): {contexto_canal}")
    if descricao_video:
        partes.append(f"Instruções específicas pra esse vídeo: {descricao_video}")

    mensagens = [
        {"role": "system", "content": PROMPT_SISTEMA},
        {"role": "user", "content": "\n".join(partes)},
    ]
    return _chamar_pollinations(mensagens, tentativas)


PROMPT_SISTEMA_TAGS = (
    "Você sugere hashtags e tags de YouTube em português do Brasil pra ajudar um vídeo a "
    "viralizar/ser recomendado. Responda só com uma lista separada por vírgulas, sem "
    "explicação, sem numeração, sem a palavra 'hashtag'. Misture 2-3 tags bem genéricas e "
    "populares (ex: fyp, curiosidades, viral) com o resto específicas do assunto do vídeo."
)


def gerar_hashtags(titulo: str, roteiro: str = "", quantidade: int = 10, tentativas: int = 3) -> list[str]:
    """Sugestões de hashtags/tags pro vídeo. Ainda não são inseridas sozinhas no
    YouTube (depende da integração com a YouTube Data API, que envia `tags` e
    `description` no upload) — por enquanto ficam disponíveis pra você copiar."""
    mensagens = [
        {"role": "system", "content": PROMPT_SISTEMA_TAGS},
        {
            "role": "user",
            "content": f"Título do vídeo: {titulo}\nTrecho do roteiro: {roteiro[:400]}\nSugira {quantidade} hashtags/tags.",
        },
    ]
    texto = _chamar_pollinations(mensagens, tentativas)
    brutas = [t.strip().lstrip("#") for t in texto.replace("\n", ",").split(",")]
    return [t for t in brutas if t][:quantidade]
