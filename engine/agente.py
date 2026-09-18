"""O "Agente": sugere ideias de título de vídeo pro canal, opcionalmente
inspirado no que está em alta no YouTube agora, e responde pedidos livres em
texto (perguntas sobre o canal, ou comandos simples como reagendar um vídeo).
Usa a mesma API de texto gratuita da Pollinations que o roteiro."""

import json

from engine.roteiro import chamar_pollinations

PROMPT_SISTEMA = (
    "Você sugere ideias de título de vídeo pra um canal de YouTube em português do Brasil. "
    "Responda só com uma lista, um título por linha, sem numeração, sem explicação, sem aspas. "
    "Títulos curtos, com gancho de curiosidade, no estilo do nicho/tom descrito. "
    "Não copie os títulos em alta que forem mencionados — use só como pista do que está "
    "engajando agora, adaptando pro nicho do canal."
)


def sugerir_ideias(contexto_canal: str = "", tendencias: list = None, quantidade: int = 6, titulos_existentes: list = None) -> list:
    partes = [f"Sugira {quantidade} ideias de título de vídeo."]
    if contexto_canal:
        partes.append(f"Nicho/tom do canal: {contexto_canal}")
    else:
        partes.append("Sem nicho definido — pode ser curiosidades/fatos interessantes em geral.")
    if tendencias:
        partes.append("Títulos em alta no YouTube agora (só de referência, não copiar):\n" + "\n".join(tendencias[:15]))

    if titulos_existentes:
        partes.append(
            "Vídeos que o canal JÁ tem (não repita nem sugira o mesmo assunto/ângulo, nem continuação óbvia):\n"
            + "\n".join(titulos_existentes[:60])
        )

    mensagens = [
        {"role": "system", "content": PROMPT_SISTEMA},
        {"role": "user", "content": "\n\n".join(partes)},
    ]
    texto = chamar_pollinations(mensagens, tentativas=4)
    linhas = [linha.strip(" -•\t") for linha in texto.split("\n")]
    return [linha for linha in linhas if linha][:quantidade]


PROMPT_SISTEMA_LIVRE = (
    "Você é o assistente de um canal de YouTube, dentro de um app local de automação de vídeos. "
    "O usuário escreve um pedido em português (pode ser pergunta, pedido de ideias, ou comando). "
    "Você recebe o nicho/tom do canal e a lista de vídeos já gerados (com slug e data de postagem). "
    "Responda SEMPRE com um único objeto JSON válido, sem markdown, sem texto fora dele, num destes formatos:\n"
    '{"acao": "responder", "texto": "..."} — pra responder pergunta, dar ideias/sugestões, ou qualquer '
    "pedido que não seja claramente mudar a data de um vídeo específico.\n"
    '{"acao": "reagendar", "slug": "...", "data_postagem": "AAAA-MM-DD", "hora_postagem": "HH:MM ou null", '
    '"texto": "confirmação curta pro usuário"} — só quando o pedido for claramente pra mudar a data/hora '
    "de postagem de um vídeo específico que está na lista (ache o slug pelo título mais parecido).\n"
    '{"acao": "cancelar", "slug": "...", "texto": "confirmação curta"} — quando o usuário pedir pra cancelar, '
    "excluir ou remover a postagem/vídeo da fila (ache o slug pelo título mais parecido; isso apaga o vídeo).\n"
    '{"acao": "editar", "slug": "...", "titulo": "novo título ou null", "descricao_youtube": "descrição completa pro YouTube ou null", '
    '"privacidade": "private|unlisted|public ou null", "tags": ["..."] ou null, "thumbnail_texto": "texto da thumbnail ou null", '
    '"texto": "confirmação curta"} — quando o usuário pedir pra mudar/melhorar o título, a descrição, as tags, a privacidade '
    "ou o texto da thumbnail de um vídeo da lista. Preencha SÓ o que ele pediu (o resto null). Se pediu pra 'melhorar' ou "
    "'escrever' a descrição, ESCREVA você mesmo uma descrição envolvente (2-4 parágrafos curtos, com chamada pra se inscrever "
    "e algumas hashtags no fim) em descricao_youtube; se pediu pra melhorar o título, proponha um título melhor (até 100 caracteres).\n"
    "Se o pedido mencionar um vídeo que não existe na lista, ou não deixar claro qual data/vídeo, "
    'use "acao": "responder" explicando o que faltou — nunca invente um slug que não estava na lista.'
)


def responder_livre(mensagem: str, contexto_canal: str = "", videos: list | None = None) -> dict:
    """Interpreta um pedido em texto livre. Retorna sempre um dict com "acao"
    ("responder" ou "reagendar") e "texto"; se for "reagendar", também vêm
    "slug"/"data_postagem"/"hora_postagem" — quem chama ainda precisa validar
    esses campos antes de aplicar (o modelo pode errar ou alucinar)."""
    videos = videos or []
    linhas_videos = [
        f'- slug={v["slug"]} | título="{v["titulo"]}" | data atual='
        + (f'{v.get("data_postagem")} {v["hora_postagem"]}' if v.get("hora_postagem") else str(v.get("data_postagem") or "sem data"))
        for v in videos
    ]

    partes = [f"Pedido do usuário: {mensagem}"]
    partes.append(f"Nicho/tom do canal: {contexto_canal}" if contexto_canal else "Sem nicho definido pro canal.")
    partes.append("Vídeos do canal:\n" + "\n".join(linhas_videos) if linhas_videos else "O canal ainda não tem nenhum vídeo gerado.")

    mensagens = [
        {"role": "system", "content": PROMPT_SISTEMA_LIVRE},
        {"role": "user", "content": "\n\n".join(partes)},
    ]
    texto = chamar_pollinations(mensagens, tentativas=3)

    bruto = texto.strip()
    if bruto.startswith("```"):
        bruto = bruto.strip("`")
        if bruto.lower().startswith("json"):
            bruto = bruto[4:]
        bruto = bruto.strip()

    try:
        dados = json.loads(bruto)
        if isinstance(dados, dict) and dados.get("acao") in ("responder", "reagendar", "cancelar", "editar"):
            return dados
    except (json.JSONDecodeError, AttributeError):
        pass
    # modelo não seguiu o formato JSON pedido — trata a resposta toda como texto livre
    return {"acao": "responder", "texto": texto.strip()}


PROMPT_SISTEMA_REVISAO = (
    "Você é um editor experiente de canais de YouTube revisando um vídeo antes de ir ao ar. Recebe título, roteiro, "
    "cenas, descrição e tags atuais. Responda SEMPRE com um único objeto JSON válido, sem markdown, neste formato:\n"
    '{"resumo": "avaliação curta (1-2 frases)", "titulo": "título melhor (até 100 caracteres) ou null se o atual já está bom", '
    '"descricao_youtube": "descrição completa e envolvente (2-4 parágrafos curtos, chamada pra se inscrever, hashtags no fim) ou null", '
    '"tags": ["tag1", "tag2"] ou null, "thumbnail_texto": "texto curto e chamativo pra thumbnail (até 5 palavras) ou null", '
    '"observacoes": ["problemas do ROTEIRO ou das CENAS que exigem regenerar o vídeo (erro de fato, trecho confuso, cena repetida...)"]}\n'
    "Só sugira mudar o que realmente melhora; use null no que está bom. Não invente fatos novos na descrição além do que o roteiro diz."
)


def revisar_video(titulo: str, roteiro: str, descricao_atual: str, tags: str, cenas: list, thumbnail_texto: str, contexto_canal: str = "") -> dict:
    """Revisão editorial de um vídeo pronto. Devolve sugestões de título/descrição/tags/thumbnail
    (aplicáveis sem regenerar) e observações sobre roteiro/cenas (que exigem regenerar)."""
    partes = [
        f"Título atual: {titulo}",
        f"Texto atual da thumbnail: {thumbnail_texto}",
        f"Tags atuais: {tags or '(nenhuma)'}",
        f"Descrição atual: {descricao_atual or '(usa o próprio roteiro como descrição)'}",
        f"Nicho/tom do canal: {contexto_canal}" if contexto_canal else "",
        "Roteiro:\n" + roteiro[:6000],
        "Cenas (uma imagem por trecho):\n" + "\n".join(f"{i + 1}. {t[:200]}" for i, t in enumerate(cenas)),
    ]
    texto = chamar_pollinations(
        [{"role": "system", "content": PROMPT_SISTEMA_REVISAO}, {"role": "user", "content": "\n\n".join(p for p in partes if p)}],
        tentativas=3,
    )
    bruto = texto.strip()
    if bruto.startswith("```"):
        bruto = bruto.strip("`")
        if bruto.lower().startswith("json"):
            bruto = bruto[4:]
        bruto = bruto.strip()
    try:
        dados = json.loads(bruto)
        if isinstance(dados, dict):
            tags_sug = dados.get("tags")
            return {
                "resumo": str(dados.get("resumo") or ""),
                "titulo": str(dados["titulo"]).strip() if dados.get("titulo") else None,
                "descricao_youtube": str(dados["descricao_youtube"]).strip() if dados.get("descricao_youtube") else None,
                "tags": [str(t) for t in tags_sug] if isinstance(tags_sug, list) and tags_sug else None,
                "thumbnail_texto": str(dados["thumbnail_texto"]).strip() if dados.get("thumbnail_texto") else None,
                "observacoes": [str(o) for o in (dados.get("observacoes") or []) if o][:6],
            }
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return {"resumo": texto.strip()[:600], "titulo": None, "descricao_youtube": None, "tags": None, "thumbnail_texto": None, "observacoes": []}
