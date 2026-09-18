"""Monta a legenda em .ass, com a palavra atual destacada em cor enquanto é falada
(estilo "karaokê"), do jeito que aparece em Shorts/Reels."""

from datetime import timedelta
from pathlib import Path

import edge_tts

from engine.alinhamento import palavras_alinhadas

COR_TEXTO = "F6F2E9"     # ivory — cor da palavra antes/depois de ser falada
COR_DESTAQUE = "E2793D"  # laranja do app — cor da palavra sendo falada agora
COR_CAIXA = "141310"     # fundo (caixa) atrás do texto

CONFIG_LEGENDA_PADRAO = {"modo": "karaoke", "tamanho": "m", "posicao": "baixo", "cor": COR_DESTAQUE, "caixa": True}

_CABECALHO = """[Script Info]
ScriptType: v4.00+
PlayResX: {largura}
PlayResY: {altura}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fontname},{fontsize},{primary},{secondary},{outline},{back},1,0,0,0,100,100,0,0,{borderstyle},{outlinew},0,{alignment},40,40,{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_cor(rgb_hex: str, alpha_hex: str = "00") -> str:
    """Converte 'RRGGBB' pro formato de cor do .ass: &HAABBGGRR (ordem invertida)."""
    r, g, b = rgb_hex[0:2], rgb_hex[2:4], rgb_hex[4:6]
    return f"&H{alpha_hex}{b}{g}{r}"


def _formatar_tempo_ass(td: timedelta) -> str:
    total_cs = round(td.total_seconds() * 100)
    horas, resto = divmod(total_cs, 360_000)
    minutos, resto = divmod(resto, 6_000)
    segundos, centesimos = divmod(resto, 100)
    return f"{horas:d}:{minutos:02d}:{segundos:02d}.{centesimos:02d}"


def _texto_karaoke(grupo: list) -> str:
    partes = []
    for i, (cue, texto) in enumerate(grupo):
        # duração do destaque: até a próxima palavra começar (cobre a pausa entre elas)
        if i < len(grupo) - 1:
            duracao = grupo[i + 1][0].start - cue.start
        else:
            duracao = cue.end - cue.start
        centesimos = max(1, round(duracao.total_seconds() * 100))
        texto_limpo = texto.replace("{", "").replace("}", "")
        partes.append(f"{{\\k{centesimos}}}{texto_limpo} ")
    return "".join(partes).strip()


def gerar_ass(
    submaker: edge_tts.SubMaker,
    caminho: Path,
    largura: int,
    altura: int,
    fontsize: int,
    marginv: int,
    palavras_por_legenda: int,
    roteiro: str,
    fontname: str = "Segoe UI",
    config: dict | None = None,
) -> Path:
    """Agrupa as palavras em blocos curtos e grava um .ass. `config` (todos opcionais):
    modo "karaoke" (palavra atual destacada) | "simples"; tamanho "p"|"m"|"g";
    posicao "baixo"|"meio"|"topo"; cor (hex do destaque); caixa (fundo atrás do texto)."""
    cfg = {**CONFIG_LEGENDA_PADRAO, **(config or {})}
    fontsize = round(fontsize * {"p": 0.8, "m": 1.0, "g": 1.25}.get(cfg["tamanho"], 1.0))
    alinhamento = {"baixo": 2, "meio": 5, "topo": 8}.get(cfg["posicao"], 2)
    if alinhamento == 5:
        marginv = 0
    elif alinhamento == 8:
        marginv = max(marginv, round(altura * 0.06))
    cor_destaque = cfg["cor"] if len(str(cfg["cor"]).lstrip("#")) == 6 else COR_DESTAQUE
    cor_destaque = str(cor_destaque).lstrip("#")
    karaoke = cfg["modo"] != "simples"
    cues = submaker.cues
    textos = palavras_alinhadas(cues, roteiro)
    pares = list(zip(cues, textos))

    eventos = []
    for i in range(0, len(pares), palavras_por_legenda):
        grupo = pares[i : i + palavras_por_legenda]
        if not grupo:
            continue
        inicio = _formatar_tempo_ass(grupo[0][0].start)
        fim = _formatar_tempo_ass(grupo[-1][0].end)
        texto = _texto_karaoke(grupo) if karaoke else " ".join(t.replace("{", "").replace("}", "") for _, t in grupo)
        eventos.append(f"Dialogue: 0,{inicio},{fim},Default,,0,0,0,,{texto}")

    cabecalho = _CABECALHO.format(
        largura=largura,
        altura=altura,
        fontname=fontname,
        fontsize=fontsize,
        # No .ass, o \k mostra a "SecondaryColour" ANTES da palavra ser dita e
        # troca pra "PrimaryColour" quando o tempo dela chega — por isso o
        # destaque (cor de "já falado") vai em primary, e o normal em secondary.
        primary=_ass_cor(cor_destaque if karaoke else COR_TEXTO),
        secondary=_ass_cor(COR_TEXTO),
        outline=_ass_cor("000000"),
        back=_ass_cor(COR_CAIXA, "40"),
        marginv=marginv,
        alignment=alinhamento,
        borderstyle=3 if cfg["caixa"] else 1,
        outlinew=0 if cfg["caixa"] else 4,
    )

    caminho.write_text(cabecalho + "\n".join(eventos) + "\n", encoding="utf-8")
    return caminho
