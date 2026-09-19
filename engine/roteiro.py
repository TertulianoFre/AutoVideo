"""Gera o roteiro e as hashtags automaticamente a partir de um título, usando a
API de texto gratuita da Pollinations.ai (compatível com o formato da OpenAI,
sem chave)."""

import re
import time

import requests

POLLINATIONS_CHAT_URL = "https://text.pollinations.ai/openai"

# Ritmo médio de fala do edge-tts nas vozes usadas aqui — usado tanto pra pedir
# o roteiro do tamanho certo quanto pro aviso de duração em pipeline.py.
PALAVRAS_POR_MINUTO = 165  # ritmo medido da narração (≈ 2,8 palavras/s)

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


def chamar_pollinations(mensagens: list, tentativas: int = 4) -> str:
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
                texto = (escolhas[0].get("message", {}).get("content", "") if escolhas else "")
                # o modelo às vezes vaza tokens especiais tipo <|endoftext|> no texto
                texto = re.sub(r"<\|[^|>]*\|>", "", texto).strip()
                if texto:
                    return texto
                ultimo_erro = f"resposta sem conteúdo: {str(dados)[:200]}"
            else:
                ultimo_erro = f"HTTP {resposta.status_code}: {resposta.text[:200]}"
        except (requests.RequestException, ValueError) as erro:
            ultimo_erro = str(erro)
        time.sleep(2 * tentativa)
    raise RuntimeError(f"Chamada à Pollinations falhou {tentativas}x ({ultimo_erro})")


PROMPT_SISTEMA_REVISAO = (
    "Você revisa roteiros de narração em português do Brasil. Corrija erros de "
    "gramática, concordância e frases estranhas, artificiais ou mal construídas, "
    "mantendo o mesmo sentido, a mesma estrutura, o mesmo tom e aproximadamente o "
    "mesmo tamanho. Não resuma, não adicione nem remova ideias — só melhore a "
    "fluência de quem vai narrar isso em voz alta. Responda só com o texto "
    "revisado, sem comentários, sem explicações, sem aspas."
)


def _revisar_roteiro(roteiro: str, tentativas: int = 2) -> str:
    """Segunda passada pedindo pro modelo revisar o próprio texto — o modelo é
    pequeno e às vezes escreve frase torta na primeira tentativa, mas revisar
    um texto pronto costuma sair melhor do que escrever direto. Revisão é um
    bônus: se falhar ou vier estranha (tamanho muito diferente do original,
    sinal de que resumiu/alucinou), mantém o roteiro original em vez de arriscar."""
    try:
        revisado = chamar_pollinations(
            [
                {"role": "system", "content": PROMPT_SISTEMA_REVISAO},
                {"role": "user", "content": roteiro},
            ],
            tentativas,
        )
    except RuntimeError:
        return roteiro

    proporcao = len(revisado.split()) / max(1, len(roteiro.split()))
    if not revisado or not (0.7 <= proporcao <= 1.3):
        return roteiro
    return revisado


def gerar_roteiro(
    titulo: str,
    duracao_alvo_minutos: float = 1.0,
    contexto_canal: str = "",
    descricao_video: str = "",
    tentativas: int = 3,
    num_cenas: int | None = None,
    cenas_midia: list | None = None,
) -> str:
    palavras_alvo = round(duracao_alvo_minutos * PALAVRAS_POR_MINUTO)

    partes = [f"Escreva um roteiro de aproximadamente {palavras_alvo} palavras sobre: {titulo}"]
    if contexto_canal:
        partes.append(f"Contexto do canal (nicho, tom, público — mantenha o roteiro alinhado com isso): {contexto_canal}")
    if descricao_video:
        partes.append(f"Instruções específicas pra esse vídeo: {descricao_video}")

    if cenas_midia:
        # o vídeo terá uma imagem/vídeo escolhido por você em cada cena: cada parágrafo narra o que aparece nela
        n_total = max(num_cenas or 0, len(cenas_midia))
        lista = "\n".join(f"Cena {i + 1}: {d}" for i, d in enumerate(cenas_midia))
        extra = "" if n_total == len(cenas_midia) else f" As cenas {len(cenas_midia) + 1} a {n_total} não têm imagem definida: continue o assunto naturalmente."
        partes.append(
            f"O vídeo terá {n_total} cenas, cada uma com uma imagem/vídeo já escolhido, nesta ordem:\n{lista}\n"
            f"Escreva EXATAMENTE {n_total} parágrafos, separados por uma linha em branco: o parágrafo N narra o que aparece na cena N "
            f"(use o que está descrito, sem inventar detalhes visuais que contradigam) e liga naturalmente com o anterior.{extra}"
        )
        num_cenas = n_total
    elif num_cenas and num_cenas > 1:
        partes.append(
            f"ESTRUTURA OBRIGATÓRIA: escreva EXATAMENTE {num_cenas} parágrafos, separados por uma linha em branco. "
            "Cada parágrafo é um assunto/cena distinto (se o vídeo for de curiosidades, uma curiosidade por parágrafo), "
            "e cada um vira uma cena com uma imagem própria. Não use títulos nem numeração."
        )

    mensagens = [
        {"role": "system", "content": PROMPT_SISTEMA},
        {"role": "user", "content": "\n".join(partes)},
    ]
    rascunho = chamar_pollinations(mensagens, tentativas)
    rascunho = _ajustar_tamanho(mensagens, rascunho, palavras_alvo, tentativas, num_cenas)
    if (num_cenas and num_cenas > 1) or cenas_midia:
        return rascunho  # a revisão junta parágrafos; aqui a estrutura em blocos é o que importa
    return _revisar_roteiro(rascunho)


def _ajustar_tamanho(mensagens: list, roteiro: str, alvo: int, tentativas: int, num_cenas: int | None = None) -> str:
    """O modelo costuma escrever bem menos (ou mais) que o pedido. Se ficar
    fora de -15%/+20% da meta, pede uma reescrita e fica com a versão mais
    próxima da meta (até 2 rodadas)."""
    for _ in range(2):
        n = len(roteiro.split())
        if alvo * 0.85 <= n <= alvo * 1.2:
            break
        if n < alvo * 0.85:
            pedido = (
                f"O roteiro tem {n} palavras e precisa ter cerca de {alvo}. Reescreva-o COMPLETO, "
                f"desenvolvendo mais cada ponto (detalhes, exemplos, curiosidades), sem repetir frases, "
                f"até chegar perto de {alvo} palavras. Responda só com o roteiro."
            )
        else:
            pedido = f"O roteiro tem {n} palavras e precisa ter cerca de {alvo}. Reescreva-o COMPLETO, mais enxuto, mantendo o essencial. Responda só com o roteiro."
        if num_cenas and num_cenas > 1:
            pedido += f" Mantenha EXATAMENTE {num_cenas} parágrafos separados por linha em branco."
        novo = chamar_pollinations(mensagens + [{"role": "assistant", "content": roteiro}, {"role": "user", "content": pedido}], tentativas)
        if abs(len(novo.split()) - alvo) >= abs(n - alvo):
            break
        roteiro = novo
    return roteiro


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
    texto = chamar_pollinations(mensagens, tentativas)
    brutas = [t.strip().lstrip("#") for t in texto.replace("\n", ",").split(",")]
    return [t for t in brutas if t][:quantidade]


def _hashtags_de(tags: list, limite: int = 8) -> str:
    return " ".join("#" + "".join(t.split()) for t in tags[:limite] if t.strip())


def descricao_basica(titulo: str, roteiro: str, tags: list) -> str:
    """Descrição simples montada sem IA (plano B): abertura do roteiro + chamada + hashtags."""
    frases = re.split(r"(?<=[.!?])\s+", " ".join(roteiro.split()))
    abertura = " ".join(frases[:2]).strip() or titulo
    partes = [abertura, "Gostou? Deixe o seu like, se inscreva no canal e conte aqui nos comentários o que achou!"]
    hashtags = _hashtags_de(tags)
    if hashtags:
        partes.append(hashtags)
    return "\n\n".join(partes)[:4900]


def gerar_descricao(titulo: str, roteiro: str, tags: list, contexto_canal: str = "", tentativas: int = 2) -> str:
    """Descrição pro YouTube (gancho + resumo do que o vídeo mostra + chamada + hashtags).
    Se a IA falhar ou vier estranha, cai na descricao_basica."""
    try:
        texto = chamar_pollinations(
            [
                {"role": "system", "content": (
                    "Você escreve descrições de vídeo de YouTube em português do Brasil. Formato: 1) um gancho de 1-2 frases "
                    "com a palavra-chave do título; 2) 2-3 linhas resumindo o que o vídeo mostra, usando SÓ o que está no roteiro "
                    "(não invente fatos); 3) uma chamada pra curtir, se inscrever e comentar; 4) 5 a 8 hashtags no fim. "
                    "Máximo 1200 caracteres. Responda só com a descrição, sem aspas e sem títulos."
                )},
                {"role": "user", "content": f"Título: {titulo}\n" + (f"Canal: {contexto_canal}\n" if contexto_canal else "") + f"Roteiro:\n{roteiro[:4000]}"},
            ],
            tentativas,
        ).strip()
    except RuntimeError:
        texto = ""
    if not (80 <= len(texto) <= 4900):
        return descricao_basica(titulo, roteiro, tags)
    return texto
