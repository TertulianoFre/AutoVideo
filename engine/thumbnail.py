"""Gera a thumbnail do vídeo: a primeira imagem de cena (16:9) com o título em
destaque por cima, no estilo de thumbnail de YouTube — texto grande, poucas
palavras visíveis de uma vez, alto contraste."""

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LARGURA, ALTURA = 1280, 720
COR_TEXTO = (246, 242, 233)
COR_CAIXA = (20, 19, 15)

_CAMINHOS_FONTE = [
    "C:/Windows/Fonts/seguisb.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    for caminho in _CAMINHOS_FONTE:
        if Path(caminho).exists():
            return ImageFont.truetype(caminho, tamanho)
    return ImageFont.load_default()


def cor_de_hex(hex_str: str) -> tuple[int, int, int] | None:
    """"FFD23F" ou "#FFD23F" -> (255, 210, 63); None se vazio/inválido (cai no padrão)."""
    hex_str = (hex_str or "").strip().lstrip("#")
    if len(hex_str) != 6:
        return None
    try:
        return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


POSICOES = [
    "topo-esquerda", "topo-centro", "topo-direita",
    "centro-esquerda", "centro", "centro-direita",
    "baixo-esquerda", "baixo-centro", "baixo-direita",
]
_FRACAO_VERTICAL = {"topo": 0.18, "centro": 0.5, "baixo": 0.82}
TAMANHOS = {"pequeno": 60, "medio": 80, "grande": 104}
MARGEM_HORIZONTAL = 60


def _posicao_valida(posicao: str) -> str:
    return posicao if posicao in POSICOES else "baixo-centro"


def gerar_thumbnail(
    imagem_base: Path,
    titulo: str,
    caminho_saida: Path,
    cor_texto: tuple[int, int, int] | None = None,
    posicao: str = "baixo-centro",
    tamanho_fonte: int = 80,
) -> Path:
    cor = cor_texto or COR_TEXTO
    partes = _posicao_valida(posicao).split("-")
    vertical, horizontal = (partes[0], "centro") if len(partes) == 1 else partes
    tamanho_fonte = max(30, min(140, tamanho_fonte))
    base = Image.open(imagem_base).convert("RGB").resize((LARGURA, ALTURA), Image.LANCZOS)

    fonte = _fonte(tamanho_fonte)
    largura_chars = max(8, round(16 * 80 / tamanho_fonte))
    linhas = textwrap.wrap(titulo.upper(), width=largura_chars)[:3]

    altura_linha = round(tamanho_fonte * 1.12)
    altura_bloco = len(linhas) * altura_linha
    ancora_y = ALTURA * _FRACAO_VERTICAL[vertical]
    y_inicial = min(max(ancora_y - altura_bloco / 2, 20), ALTURA - altura_bloco - 20)

    # escurece uma faixa horizontal em volta do texto (onde quer que ele esteja)
    # pra ficar legível em cima de qualquer imagem de fundo
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    desenho_overlay = ImageDraw.Draw(overlay)
    centro_faixa = y_inicial + altura_bloco / 2
    meia_faixa = altura_bloco / 2 + 90
    for y in range(max(0, int(centro_faixa - meia_faixa)), min(ALTURA, int(centro_faixa + meia_faixa))):
        distancia = abs(y - centro_faixa) / meia_faixa
        alpha = int(220 * max(0, 1 - distancia))
        desenho_overlay.line([(0, y), (LARGURA, y)], fill=(*COR_CAIXA, alpha))
    imagem = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

    desenho = ImageDraw.Draw(imagem)
    y = y_inicial
    for linha in linhas:
        caixa = desenho.textbbox((0, 0), linha, font=fonte)
        largura_linha = caixa[2] - caixa[0]
        if horizontal == "esquerda":
            x = MARGEM_HORIZONTAL
        elif horizontal == "direita":
            x = LARGURA - MARGEM_HORIZONTAL - largura_linha
        else:
            x = (LARGURA - largura_linha) / 2
        # contorno grosso (stroke manual) pra legibilidade em qualquer fundo
        for dx, dy in [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
            desenho.text((x + dx, y + dy), linha, font=fonte, fill=COR_CAIXA)
        desenho.text((x, y), linha, font=fonte, fill=cor)
        y += altura_linha

    imagem.save(caminho_saida, "PNG")
    return caminho_saida
