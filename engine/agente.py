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


def sugerir_ideias(contexto_canal: str = "", tendencias: list = None, quantidade: int = 6) -> list:
    partes = [f"Sugira {quantidade} ideias de título de vídeo."]
    if contexto_canal:
        partes.append(f"Nicho/tom do canal: {contexto_canal}")
    else:
        partes.append("Sem nicho definido — pode ser curiosidades/fatos interessantes em geral.")
    if tendencias:
        partes.append("Títulos em alta no YouTube agora (só de referência, não copiar):\n" + "\n".join(tendencias[:15]))

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
        if isinstance(dados, dict) and dados.get("acao") in ("responder", "reagendar"):
            return dados
    except (json.JSONDecodeError, AttributeError):
        pass
    # modelo não seguiu o formato JSON pedido — trata a resposta toda como texto livre
    return {"acao": "responder", "texto": texto.strip()}
