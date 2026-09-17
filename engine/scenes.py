"""Divide o roteiro em 'cenas' (trechos de frases) pra gerar uma imagem por cena.
A imagem troca com calma ao longo do vídeo, acompanhando o assunto sendo falado,
em vez de ficar uma imagem só do início ao fim."""

from dataclasses import dataclass
from datetime import timedelta

from engine.alinhamento import palavras_alinhadas

DURACAO_MINIMA_CENA = timedelta(seconds=5)


@dataclass
class Cena:
    texto: str
    inicio: timedelta
    fim: timedelta

    @property
    def duracao_segundos(self) -> float:
        return (self.fim - self.inicio).total_seconds()


def dividir_em_cenas(submaker, roteiro: str, duracao_minima: timedelta = DURACAO_MINIMA_CENA) -> list:
    """Agrupa as palavras em cenas, cortando ao final de frases (. ? !), mas nunca
    deixando uma cena curta demais (nesse caso funde com a cena seguinte)."""
    cues = submaker.cues
    textos = palavras_alinhadas(cues, roteiro)

    cenas = []
    inicio_atual = cues[0].start
    palavras_atual = []

    for cue, palavra in zip(cues, textos):
        palavras_atual.append(palavra)
        termina_frase = palavra.rstrip().endswith((".", "?", "!"))
        duracao_atual = cue.end - inicio_atual
        if termina_frase and duracao_atual >= duracao_minima:
            cenas.append(Cena(" ".join(palavras_atual), inicio_atual, cue.end))
            palavras_atual = []
            inicio_atual = cue.end

    if palavras_atual:
        texto_restante = " ".join(palavras_atual)
        if cenas:
            ultima = cenas[-1]
            cenas[-1] = Cena(f"{ultima.texto} {texto_restante}", ultima.inicio, cues[-1].end)
        else:
            cenas.append(Cena(texto_restante, inicio_atual, cues[-1].end))

    return cenas
