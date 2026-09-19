"""Monta a legenda em .ass, com a palavra atual destacada em cor enquanto é falada
(estilo "karaokê"), do jeito que aparece em Shorts/Reels."""

from datetime import timedelta
from pathlib import Path

import edge_tts

from engine.alinhamento import palavras_alinhadas

COR_TEXTO = "F6F2E9"     # ivory — cor da palavra antes/depois de ser falada
COR_DESTAQUE = "E2793D"  # laranja do app — cor da palavra sendo falada agora
COR_CAIXA = "141310"     # fundo (caixa) atrás do texto

FUNDOS_LEGENDA = ("contorno", "caixa", "cor", "sombra")
CONFIG_LEGENDA_PADRAO = {"modo": "karaoke", "tamanho": "m", "posicao": "baixo", "cor": COR_DESTAQUE, "fundo": "caixa"}


def normalizar_config(config: dict | None) -> dict:
    """Config completa da legenda. Aceita o formato antigo (caixa True/False) e vira `fundo`."""
    config = dict(config or {})
    cfg = {**CONFIG_LEGENDA_PADRAO, **config}
    if "fundo" not in config and "caixa" in config:
        cfg["fundo"] = "caixa" if config["caixa"] else "contorno"
    if cfg["fundo"] not in FUNDOS_LEGENDA:
        cfg["fundo"] = "caixa"
    cor = str(cfg.get("cor") or "").lstrip("#")
    cfg["cor"] = cor if len(cor) == 6 else COR_DESTAQUE
    cfg.pop("caixa", None)
    return cfg


def _luminancia(hex_rgb: str) -> float:
    r, g, b = (int(hex_rgb[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

_CABECALHO = """[Script Info]
ScriptType: v4.00+
PlayResX: {largura}
PlayResY: {altura}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fontname},{fontsize},{primary},{secondary},{outline},{back},1,0,0,0,100,100,0,0,{borderstyle},{outlinew},{shadow},{alignment},40,40,{marginv},1

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


# palavras que não fecham uma linha de legenda ("... de fevereiro de 1907, num" / "passeio ..."): a linha
# ficaria pendurada esperando o resto da frase
_PALAVRAS_FRACAS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "num", "numa", "nuns", "numas", "ao", "aos", "à", "às", "e", "ou", "mas", "que", "com", "sem", "por", "para", "pra",
    "pelo", "pela", "pelos", "pelas", "se", "como", "sob", "até", "entre", "sobre", "já", "não", "seu", "sua", "seus",
    "suas", "meu", "minha", "esse", "essa", "este", "esta", "aquele", "aquela", "muito", "mais", "quando", "onde",
}


def _limpo(texto: str) -> str:
    return texto.strip().strip("\"'“”‘’()[]«»")


def _fim_de_frase(texto: str) -> bool:
    return _limpo(texto).endswith((".", "!", "?", "…", ";", ":"))


def _termina_com_virgula(texto: str) -> bool:
    return _limpo(texto).endswith(",")


def _palavra_fraca(texto: str) -> bool:
    limpo = _limpo(texto)
    return limpo.casefold() in _PALAVRAS_FRACAS and not limpo.endswith((",", ".", "!", "?", "…", ";", ":"))


def _agrupar_palavras(pares: list, maximo: int) -> list:
    """Divide as palavras em linhas de legenda de até `maximo` palavras respeitando a fala: fim de frase sempre
    fecha a linha, as linhas de uma frase ficam do mesmo tamanho (nada de 6 palavras + 1 sobrando), a quebra
    prefere cair depois de uma vírgula e nenhuma linha termina em artigo/preposição."""
    import math

    frases, atual = [], []
    for par in pares:
        atual.append(par)
        if _fim_de_frase(par[1]):
            frases.append(atual)
            atual = []
    if atual:
        frases.append(atual)

    grupos = []
    for frase in frases:
        n = len(frase)
        if n <= maximo:
            grupos.append(frase)
            continue
        partes = math.ceil(n / maximo)
        ideal = n / partes
        inicio = 0
        for j in range(1, partes):
            alvo = round(ideal * j)
            melhor = None
            for b in range(max(inicio + 2, alvo - 2), min(n - 2, alvo + 2) + 1):
                if b - inicio > maximo + 1:
                    continue
                ultima = frase[b - 1][1]
                penalidade = (0 if _termina_com_virgula(ultima) else 4 if _palavra_fraca(ultima) else 1) + abs(b - alvo) * 0.4
                if melhor is None or penalidade < melhor[0]:
                    melhor = (penalidade, b)
            corte = melhor[1] if melhor else min(max(alvo, inicio + 1), n - 1)
            grupos.append(frase[inicio:corte])
            inicio = corte
        grupos.append(frase[inicio:])
    return [g for g in grupos if g]


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
    cfg = normalizar_config(config)
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
    for grupo in _agrupar_palavras(pares, palavras_por_legenda):
        inicio = _formatar_tempo_ass(grupo[0][0].start)
        fim = _formatar_tempo_ass(grupo[-1][0].end)
        texto = _texto_karaoke(grupo) if karaoke else " ".join(t.replace("{", "").replace("}", "") for _, t in grupo)
        eventos.append(f"Dialogue: 0,{inicio},{fim},Default,,0,0,0,,{texto}")

    # ----- estilo do fundo do texto -----
    fundo = cfg["fundo"]
    respiro = max(6, round(fontsize * 0.14))
    texto_base, spoken, unspoken, outline, back = COR_TEXTO, None, None, _ass_cor("000000"), _ass_cor(COR_CAIXA, "40")
    borderstyle, outlinew, sombra = 1, 4, 0
    if fundo == "caixa":  # caixa escura translúcida
        borderstyle, outlinew, outline = 3, respiro, _ass_cor(COR_CAIXA, "38")
    elif fundo == "cor":  # caixa na cor de destaque; texto escuro ou claro conforme o contraste
        borderstyle, outlinew, outline = 3, respiro, _ass_cor(cor_destaque, "10")
        texto_base = COR_CAIXA if _luminancia(cor_destaque) > 0.55 else "FFFFFF"
    elif fundo == "sombra":  # sem caixa nem contorno: sombra suave e grande
        outlinew, sombra = 0, max(3, round(fontsize * 0.06))
        back = _ass_cor("000000", "50")
    if fundo == "cor":
        # karaokê: palavra ainda não falada mais apagada, a falada em cor cheia
        primary, secondary = _ass_cor(texto_base), _ass_cor(texto_base, "80" if karaoke else "00")
    else:
        # No .ass, o \k mostra a "SecondaryColour" ANTES da palavra ser dita e troca pra
        # "PrimaryColour" quando o tempo dela chega — por isso o destaque vai em primary.
        primary = _ass_cor(cor_destaque if karaoke else COR_TEXTO)
        secondary = _ass_cor(COR_TEXTO)

    cabecalho = _CABECALHO.format(
        largura=largura,
        altura=altura,
        fontname=fontname,
        fontsize=fontsize,
        primary=primary,
        secondary=secondary,
        outline=outline,
        back=back,
        marginv=marginv,
        alignment=alinhamento,
        borderstyle=borderstyle,
        outlinew=outlinew,
        shadow=sombra,
    )

    caminho.write_text(cabecalho + "\n".join(eventos) + "\n", encoding="utf-8")
    return caminho
