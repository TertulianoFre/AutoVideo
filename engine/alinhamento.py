"""Alinha as palavras originais do roteiro (com pontuação) com as marcações de
tempo do edge-tts, que vêm sem pontuação."""


def palavras_alinhadas(cues: list, roteiro: str) -> list:
    palavras_originais = roteiro.split()
    if len(palavras_originais) == len(cues):
        return palavras_originais
    return [cue.content for cue in cues]
