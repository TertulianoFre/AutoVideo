"""Gera a thumbnail do vídeo: a primeira imagem de cena (16:9) com o título em
destaque por cima, no estilo de thumbnail de YouTube — texto grande, poucas
palavras visíveis de uma vez, alto contraste."""

import textwrap
from pathlib import Path

import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

LARGURA, ALTURA = 1280, 720
COR_TEXTO = (246, 242, 233)
COR_CAIXA = (20, 19, 15)

_CAMINHOS_FONTE = [
    "C:/Windows/Fonts/seguisb.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _fonte(tamanho: int, pesada: bool = False) -> ImageFont.FreeTypeFont:
    for caminho in (["C:/Windows/Fonts/impact.ttf"] if pesada else []) + _CAMINHOS_FONTE:
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
TAMANHOS = {"pequeno": 60, "medio": 80, "grande": 104}  # mantido só de fallback pra thumbnails antigas
TAMANHO_FONTE_MIN, TAMANHO_FONTE_MAX = 24, 190
MARGEM_HORIZONTAL = 60


EFEITOS = ["nenhum", "sombra", "neon", "explosao", "youtuber"]


def _raios(imagem: Image.Image) -> Image.Image:
    """Feixes de luz saindo dos cantos, como nas thumbnails de YouTuber."""
    largura, altura = imagem.size
    camada = Image.new("RGBA", imagem.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    comp = max(largura, altura) * 0.42
    cantos = ((0, 0, 0), (largura, 0, 180), (0, altura, 0), (largura, altura, 180))
    for i, (ox, oy, base_ang) in enumerate(cantos):
        sinal = 1 if oy == 0 else -1
        for ang, meia in ((14, 1.3), (32, 2.2), (58, 1.6)):
            a = math.radians(base_ang + (ang if ox == 0 else -ang) * sinal)
            p1 = (ox + math.cos(a - math.radians(meia)) * comp, oy + math.sin(a - math.radians(meia)) * comp)
            p2 = (ox + math.cos(a + math.radians(meia)) * comp, oy + math.sin(a + math.radians(meia)) * comp)
            d.polygon([(ox, oy), p1, p2], fill=(255, 255, 255, 70))
    return Image.alpha_composite(imagem.convert("RGBA"), camada.filter(ImageFilter.GaussianBlur(3))).convert("RGB")


def cobrir(imagem: Image.Image, tamanho: tuple[int, int]) -> Image.Image:
    """Redimensiona preenchendo o quadro e corta o excesso (nunca distorce)."""
    largura, altura = tamanho
    escala = max(largura / imagem.width, altura / imagem.height)
    nova = imagem.resize((round(imagem.width * escala), round(imagem.height * escala)), Image.LANCZOS)
    esq, topo = (nova.width - largura) // 2, (nova.height - altura) // 2
    return nova.crop((esq, topo, esq + largura, topo + altura))


def _efeito_atras(imagem: Image.Image, blocos: list, fonte, cor, efeito: str, caixa: tuple) -> Image.Image:
    """Desenha o efeito ATRÁS do texto. blocos = [(x, y, linha)]; caixa = (x0, y0, x1, y1) do bloco."""
    camada = Image.new("RGBA", imagem.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    if efeito == "sombra":
        for x, y, linha in blocos:
            d.text((x + 8, y + 10), linha, font=fonte, fill=(0, 0, 0, 200))
        camada = camada.filter(ImageFilter.GaussianBlur(6))
    elif efeito == "neon":
        for x, y, linha in blocos:
            d.text((x, y), linha, font=fonte, fill=(*cor, 255), stroke_width=6, stroke_fill=(*cor, 255))
        largo, medio = camada.filter(ImageFilter.GaussianBlur(26)), camada.filter(ImageFilter.GaussianBlur(10))
        camada = Image.alpha_composite(Image.alpha_composite(largo, largo), medio)
    elif efeito == "explosao":
        cx, cy = (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2
        rx, ry = (caixa[2] - caixa[0]) / 2 + 70, (caixa[3] - caixa[1]) / 2 + 70
        pontos = 22
        forma = []
        for i in range(pontos * 2):
            f = 1.0 if i % 2 == 0 else 0.68
            ang = math.pi * i / pontos
            forma.append((cx + math.cos(ang) * rx * f, cy + math.sin(ang) * ry * f))
        d.polygon(forma, fill=(255, 92, 33, 255), outline=(20, 19, 15, 255))
        interno = [(cx + (px - cx) * 0.8, cy + (py - cy) * 0.8) for px, py in forma]
        d.polygon(interno, fill=(190, 25, 35, 255))
    return Image.alpha_composite(imagem.convert("RGBA"), camada).convert("RGB")


def _posicao_valida(posicao: str) -> str:
    return posicao if posicao in POSICOES else "baixo-centro"


def gerar_thumbnail(
    imagem_base: Path,
    titulo: str,
    caminho_saida: Path,
    cor_texto: tuple[int, int, int] | None = None,
    posicao: str = "baixo-centro",
    tamanho_fonte: int = 80,
    pos_livre: tuple[float, float] | None = None,
    tamanho: tuple[int, int] = (LARGURA, ALTURA),
    efeito: str = "nenhum",
) -> Path:
    """pos_livre: (fracao_x, fracao_y) do CENTRO do bloco de texto, cada um de
    0.0 a 1.0 — posição arrastável de verdade, em vez da grade de 9 pontos.
    Quando dado, sobrepõe `posicao` (que continua sendo o padrão/fallback pra
    thumbnails antigas). Com pos_livre, o texto sempre fica centralizado no
    ponto X escolhido (arrastar não tem conceito de "alinhar à esquerda")."""
    LARGURA, ALTURA = tamanho  # vertical (Shorts) usa outro tamanho de tela
    cor = cor_texto or COR_TEXTO
    tamanho_fonte = max(TAMANHO_FONTE_MIN, min(TAMANHO_FONTE_MAX, tamanho_fonte))
    base = Image.open(imagem_base).convert("RGB")
    base = cobrir(base, (LARGURA, ALTURA))
    if not (titulo or "").strip():  # sem texto: só a imagem, sem a faixa escura nem nada por cima
        base.save(caminho_saida, "PNG")
        return caminho_saida

    fonte = _fonte(tamanho_fonte, pesada=efeito == "youtuber")
    if efeito == "youtuber":
        base = _raios(base)
    largura_chars = max(8, round(16 * 80 / tamanho_fonte))
    linhas = textwrap.wrap(titulo.upper(), width=largura_chars)[:3]

    altura_linha = round(tamanho_fonte * 1.12)
    altura_bloco = len(linhas) * altura_linha

    if pos_livre is not None:
        fracao_x, fracao_y = pos_livre
        centro_x = LARGURA * min(max(fracao_x, 0.0), 1.0)
        ancora_y = ALTURA * min(max(fracao_y, 0.0), 1.0)
        horizontal = "livre"
    else:
        partes = _posicao_valida(posicao).split("-")
        vertical, horizontal = (partes[0], "centro") if len(partes) == 1 else partes
        centro_x = None
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
    blocos = []
    y = y_inicial
    for linha in linhas:
        caixa = desenho.textbbox((0, 0), linha, font=fonte)
        largura_linha = caixa[2] - caixa[0]
        if horizontal == "esquerda":
            x = MARGEM_HORIZONTAL
        elif horizontal == "direita":
            x = LARGURA - MARGEM_HORIZONTAL - largura_linha
        elif horizontal == "livre":
            x = min(max(centro_x - largura_linha / 2, MARGEM_HORIZONTAL), LARGURA - MARGEM_HORIZONTAL - largura_linha)
        else:
            x = (LARGURA - largura_linha) / 2
        blocos.append((x, y, linha, largura_linha))
        y += altura_linha

    if efeito in EFEITOS and efeito != "nenhum" and blocos:
        caixa_bloco = (min(b[0] for b in blocos), y_inicial, max(b[0] + b[3] for b in blocos), y_inicial + altura_bloco)
        imagem = _efeito_atras(imagem, [b[:3] for b in blocos], fonte, cor, efeito, caixa_bloco)
        desenho = ImageDraw.Draw(imagem)

    if efeito == "youtuber":
        contorno = max(8, tamanho_fonte // 9)
        for i, (x, y, linha, _) in enumerate(blocos):
            amarelo = i == 0
            desenho.text((x + contorno // 2 + 4, y + contorno // 2 + 8), linha, font=fonte, fill=(0, 0, 0), stroke_width=contorno)
            desenho.text((x, y), linha, font=fonte, fill=(0, 0, 0), stroke_width=contorno)
            if amarelo:
                mascara = Image.new("L", imagem.size, 0)
                ImageDraw.Draw(mascara).text((x, y), linha, font=fonte, fill=255)
                topo, base_cor = (255, 236, 110), (cor if cor_texto else (255, 150, 20))
                grad = Image.new("RGB", (1, altura_linha + 2))
                for k in range(altura_linha + 2):
                    t = k / (altura_linha + 1)
                    grad.putpixel((0, k), tuple(round(topo[c] * (1 - t) + base_cor[c] * t) for c in range(3)))
                grad = grad.resize((imagem.width, altura_linha + 2))
                camada_cor = Image.new("RGB", imagem.size)
                camada_cor.paste(grad, (0, int(y)))
                imagem.paste(camada_cor, (0, 0), mascara)
            else:
                desenho.text((x, y), linha, font=fonte, fill=(255, 255, 255))
        blocos = []

    for x, y, linha, _ in blocos:
        # contorno grosso (stroke manual) pra legibilidade em qualquer fundo
        for dx, dy in [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
            desenho.text((x + dx, y + dy), linha, font=fonte, fill=COR_CAIXA)
        desenho.text((x, y), linha, font=fonte, fill=cor)

    imagem.save(caminho_saida, "PNG")
    return caminho_saida


TAMANHO_SHORTS = (1080, 1920)


def config_shorts(metadados: dict, padrao_titulo: str) -> dict:
    """Configuração da thumbnail vertical: o que foi salvo no editor do Short,
    ou (vídeo sem edição) o texto/cor da thumbnail normal com o efeito youtuber."""
    salvo = metadados.get("thumbnail_short") or {}
    px = salvo.get("tamanho_px")
    return {
        # texto vazio salvo de propósito = thumbnail sem texto (só cai no título quando nunca foi definido)
        "texto": salvo["texto"] if isinstance(salvo.get("texto"), str) else (metadados["thumbnail_texto"] if isinstance(metadados.get("thumbnail_texto"), str) else (metadados.get("titulo") or padrao_titulo)),
        "cor": salvo.get("cor", metadados.get("thumbnail_cor", "")),
        "tamanho_px": int(px) if isinstance(px, (int, float)) and px else 120,
        "pos_x": salvo.get("pos_x") if isinstance(salvo.get("pos_x"), (int, float)) else 0.5,
        "pos_y": salvo.get("pos_y") if isinstance(salvo.get("pos_y"), (int, float)) else 0.5,
        "efeito": salvo.get("efeito") if salvo.get("efeito") in EFEITOS else "youtuber",
        "fundo": salvo.get("fundo") if salvo.get("fundo") in ("procedural", "cena") else "procedural",
    }


def gerar_shorts(pasta: Path, metadados: dict) -> Path:
    """Gera thumbnail_shorts.png (1080x1920). Fundo procedural por padrão (sem
    imagem de IA esticada); 'cena' usa a primeira cena vertical."""
    from engine import visuals

    cfg = config_shorts(metadados, pasta.name)
    fundo = pasta / "thumbnail_shorts_fundo.png"
    if cfg["fundo"] == "cena" and (pasta / "cena00_9x16.png").exists():
        fundo = pasta / "cena00_9x16.png"
    elif not fundo.exists():
        visuals.gerar_fundo_procedural(*TAMANHO_SHORTS, fundo, semente=f"{metadados.get('titulo', pasta.name)}{metadados.get('thumbnail_short_semente', '')}")
    return gerar_thumbnail(
        fundo, cfg["texto"], pasta / "thumbnail_shorts.png", cor_de_hex(cfg["cor"]), "centro",
        cfg["tamanho_px"], (cfg["pos_x"], cfg["pos_y"]), TAMANHO_SHORTS, cfg["efeito"],
    )
