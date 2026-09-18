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


def gerar_thumbnail(imagem_base: Path, titulo: str, caminho_saida: Path) -> Path:
    base = Image.open(imagem_base).convert("RGB").resize((LARGURA, ALTURA), Image.LANCZOS)

    # escurece a parte de baixo pra o título ficar legível em cima de qualquer imagem
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    desenho_overlay = ImageDraw.Draw(overlay)
    inicio = int(ALTURA * 0.4)
    for y in range(inicio, ALTURA):
        t = (y - inicio) / max(ALTURA - inicio - 1, 1)
        alpha = int(230 * t)
        desenho_overlay.line([(0, y), (LARGURA, y)], fill=(*COR_CAIXA, alpha))
    imagem = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

    desenho = ImageDraw.Draw(imagem)
    fonte = _fonte(80)
    linhas = textwrap.wrap(titulo.upper(), width=16)[:3]

    altura_linha = 90
    y = ALTURA - 50 - len(linhas) * altura_linha
    for linha in linhas:
        caixa = desenho.textbbox((0, 0), linha, font=fonte)
        x = (LARGURA - (caixa[2] - caixa[0])) / 2
        # contorno grosso (stroke manual) pra legibilidade em qualquer fundo
        for dx, dy in [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
            desenho.text((x + dx, y + dy), linha, font=fonte, fill=COR_CAIXA)
        desenho.text((x, y), linha, font=fonte, fill=COR_TEXTO)
        y += altura_linha

    imagem.save(caminho_saida, "PNG")
    return caminho_saida
