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


def dividir_em_cenas(submaker, roteiro: str, duracao_minima: timedelta = DURACAO_MINIMA_CENA, num_cenas: int | None = None) -> list:
    """num_cenas: quantidade desejada. Agrupa frases inteiras em `num_cenas`
    blocos de duração parecida (se o roteiro tiver menos frases que isso, sai
    uma cena por frase). Sem ele, corta por frase respeitando duracao_minima."""
    if num_cenas and num_cenas > 0:
        return _dividir_em_n(submaker, roteiro, num_cenas)
    return _dividir_por_minimo(submaker, roteiro, duracao_minima)


def _dividir_em_n(submaker, roteiro: str, n: int) -> list:
    frases = _dividir_por_minimo(submaker, roteiro, timedelta(0))
    if len(frases) <= n:
        return frases
    inicio, fim = frases[0].inicio, frases[-1].fim
    total = (fim - inicio).total_seconds() or 1.0
    grupos: list[list] = [[] for _ in range(n)]
    for frase in frases:
        meio = ((frase.inicio + (frase.fim - frase.inicio) / 2) - inicio).total_seconds()
        grupos[min(n - 1, int(meio / total * n))].append(frase)
    return [
        Cena(" ".join(f.texto for f in grupo), grupo[0].inicio, grupo[-1].fim)
        for grupo in grupos
        if grupo
    ]


def _dividir_por_minimo(submaker, roteiro: str, duracao_minima: timedelta) -> list:
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
