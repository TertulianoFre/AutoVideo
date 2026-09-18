"""Alinha as palavras originais do roteiro (com pontuação) com as marcações de
tempo do edge-tts, que vêm sem pontuação."""

import re
from difflib import SequenceMatcher


def _norm(texto: str) -> str:
    return re.sub(r"\W+", "", texto.casefold())


def palavras_alinhadas(cues: list, roteiro: str) -> list:
    """Uma palavra (com pontuação) por cue. Se o número de palavras bate, é
    direto. Senão (números, hífens, siglas... o TTS divide/junta diferente),
    alinha por similaridade e devolve a palavra original — com . , ? ! — pra
    cada cue que conseguir casar; só cai no texto cru do TTS no que não casar."""
    originais = roteiro.split()
    a = [_norm(w) for w in originais]
    b = [_norm(c.content) for c in cues]
    if len(originais) == len(cues) and (a == b or not any(b)):
        return originais

    resultado = [cue.content for cue in cues]
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            for k in range(j2 - j1):
                resultado[j1 + k] = originais[i1 + k]
        elif tag == "replace" and i2 > i1 and j2 > j1:
            # uma palavra virou várias (ou o contrário): a pontuação final da
            # última palavra original vai pra última cue do trecho
            pontuacao = re.search(r"[^\w\s]+$", originais[i2 - 1])
            if pontuacao and not resultado[j2 - 1].endswith(pontuacao.group()):
                resultado[j2 - 1] += pontuacao.group()
    return resultado
