"""O "Agente": sugere ideias de título de vídeo pro canal, opcionalmente
inspirado no que está em alta no YouTube agora. Usa a mesma API de texto
gratuita da Pollinations que o roteiro."""

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
