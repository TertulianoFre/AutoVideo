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
    "Você é o FUNCIONÁRIO deste canal de YouTube, dentro de um app local de automação de vídeos. TODA pergunta do usuário é sobre "
    "ESTE canal e ESTES vídeos (o nicho, o tom e a lista de vídeos vêm abaixo) — nunca responda de forma genérica sobre YouTube: "
    "adapte ao nicho, ao público e ao que o canal já publicou (ex: se perguntarem a duração ideal de um tipo de vídeo, use as durações "
    "dos vídeos existentes e o nicho pra dar um número concreto e uma recomendação direta). Quando o usuário falar de 'o vídeo', "
    "'o último vídeo' ou citar um assunto, identifique qual é pela lista. "
    "O usuário escreve um pedido em português (pode ser pergunta, pedido de ideias, ou comando). "
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


def sugerir_duracao(titulo: str, num_cenas: int | None, descricao: str, contexto_canal: str, existentes: list) -> dict:
    """Duração recomendada (minutos) pra um vídeo desse tipo neste canal. Devolve {"minutos": float, "motivo": str}."""
    partes = [f"Título do vídeo: {titulo}"]
    if num_cenas:
        partes.append(f"Quantidade de cenas/itens: {num_cenas}")
    if descricao:
        partes.append(f"Instruções do vídeo: {descricao}")
    partes.append(f"Nicho/tom do canal: {contexto_canal}" if contexto_canal else "Canal sem nicho definido.")
    if existentes:
        partes.append("Durações dos vídeos que o canal já tem:\n" + "\n".join(existentes))
    texto = chamar_pollinations(
        [
            {"role": "system", "content": (
                "Você recomenda a duração ideal de um vídeo narrado de YouTube (roteiro lido em voz alta, imagens estáticas com transição). "
                'Responda SÓ com JSON: {"minutos": número entre 0.5 e 20, "motivo": "uma frase curta"}. Considere o tipo de vídeo, a '
                "quantidade de itens (cerca de 30-60 segundos por item em vídeos de curiosidades/listas) e o histórico do canal."
            )},
            {"role": "user", "content": "\n".join(partes)},
        ],
        tentativas=2,
    )
    bruto = texto.strip().strip("`")
    if bruto.lower().startswith("json"):
        bruto = bruto[4:]
    dados = json.loads(bruto.strip())
    minutos = min(20.0, max(0.5, float(dados["minutos"])))
    return {"minutos": round(minutos, 1), "motivo": str(dados.get("motivo") or "")}


def responder_livre(mensagem: str, contexto_canal: str = "", videos: list | None = None) -> dict:
    """Interpreta um pedido em texto livre. Retorna sempre um dict com "acao"
    ("responder" ou "reagendar") e "texto"; se for "reagendar", também vêm
    "slug"/"data_postagem"/"hora_postagem" — quem chama ainda precisa validar
    esses campos antes de aplicar (o modelo pode errar ou alucinar)."""
    videos = videos or []
    linhas_videos = []
    for v in videos:
        data = f'{v.get("data_postagem")} {v["hora_postagem"]}' if v.get("hora_postagem") else str(v.get("data_postagem") or "sem data")
        duracao = f'{round(v["duracao_segundos"] / 60, 1)} min' if v.get("duracao_segundos") else "?"
        linha = (
            f'- slug={v["slug"]} | título="{v["titulo"]}" | situação={v.get("status")} | data atual={data} | duração={duracao} '
            f'| cenas={v.get("n_cenas", "?")} | formatos={v.get("formatos", "?")} | privacidade={v.get("privacidade", "?")}'
        )
        if v.get("resumo"):
            linha += f' | roteiro começa com: "{v["resumo"]}"'
        linhas_videos.append(linha)

    from datetime import date
    partes = [f"Hoje é {date.today().isoformat()}.", f"Pedido do usuário: {mensagem}"]
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


