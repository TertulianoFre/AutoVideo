"""Gera a imagem de fundo de cada cena do vídeo — sem texto: quem carrega o
texto é a legenda.

Três estilos possíveis, escolhidos por vídeo:
  - "procedural": gradiente + halos gerados na hora, sem internet, sem custo.
  - "foto": foto real (Openverse, sem chave; Pexels também, se configurado).
  - "ia": imagem gerada por IA via Pollinations.ai — grátis, sem chave, sem
          cadastro (usa o crédito da própria Pollinations, não o seu).
"""

import hashlib
import io
import os
import random
import re
import time
import urllib.parse
from pathlib import Path

import cv2
import numpy as np
import requests
from deep_translator import MyMemoryTranslator
from PIL import Image, ImageDraw, ImageFilter

COR_FUNDO = (20, 19, 15)
COR_FUNDO_BASE = (30, 28, 22)
COR_ACCENT = (226, 121, 61)

PEXELS_URL = "https://api.pexels.com/v1/search"
OPENVERSE_URL = "https://api.openverse.org/v1/images/"
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"

# Estilo simples (não fotorrealista, sem 3D) por padrão — pedido explícito:
# desenho/cartoon 2D, mais fácil da IA acertar o assunto sem gerar anatomia
# esquisita. Dá pra pedir outra coisa (mais detalhado, infantil...) via a
# "descrição do vídeo" na tela de Novo Vídeo — vira o {extra} abaixo.
ESTILO_PROMPT_IA = (
    "{cena}, flat 2d illustration, cartoon style, flat colors, no gradients, no 3d, "
    "simple shapes, wide shot, full scene, no text, no watermark, no logo{extra}"
)

# Verbos de expressão facial intensa (bocejar, gritar...) fazem esse modelo
# gratuito gerar rostos bem distorcidos, mesmo pedindo "sem close-up". Troca por
# uma descrição de cena mais genérica antes de montar o prompt — o resto do
# texto (o assunto de verdade) continua intacto.
_SUBSTITUICOES_RISCO = {
    "yawning": "feeling very sleepy, stretching",
    "yawns": "feels very sleepy and stretches",
    "yawn": "feel very sleepy and stretch",
    "screaming": "reacting with wide-eyed surprise",
    "screams": "reacts with wide-eyed surprise",
    "scream": "react with wide-eyed surprise",
    "shouting": "gesturing with emotion",
    "shout": "gesture with emotion",
    "crying": "looking sad, wiping a tear",
    "cries": "looks sad and wipes a tear",
    "cry": "look sad and wipe a tear",
    "laughing hard": "smiling happily",
}


def _evitar_gatilhos_de_rosto(texto: str) -> str:
    resultado = texto
    for gatilho, substituto in _SUBSTITUICOES_RISCO.items():
        resultado = re.sub(re.escape(gatilho), substituto, resultado, flags=re.IGNORECASE)
    return resultado


def _traduzir_para_ingles(texto: str) -> str:
    """A IA de imagem entende MUITO melhor prompts em inglês. Traduz o texto da
    cena (grátis, via MyMemory); se a tradução falhar, usa o texto original."""
    try:
        traduzido = MyMemoryTranslator(source="pt-BR", target="en-US").translate(texto[:480])
        return traduzido or texto
    except Exception:
        return texto


# ---------------------------------------------------------------------------
# procedural (Pillow) — sem internet, sem custo
# ---------------------------------------------------------------------------

def _seed_de(texto: str) -> random.Random:
    """Gerador aleatório determinístico a partir do texto da cena — a mesma
    cena gera sempre o mesmo visual, útil se o vídeo precisar ser regenerado."""
    digest = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _gradiente_base(largura: int, altura: int) -> Image.Image:
    imagem = Image.new("RGB", (largura, altura), COR_FUNDO)
    desenho = ImageDraw.Draw(imagem)
    for y in range(altura):
        t = y / max(altura - 1, 1)
        r = int(COR_FUNDO[0] + (COR_FUNDO_BASE[0] - COR_FUNDO[0]) * t)
        g = int(COR_FUNDO[1] + (COR_FUNDO_BASE[1] - COR_FUNDO[1]) * t)
        b = int(COR_FUNDO[2] + (COR_FUNDO_BASE[2] - COR_FUNDO[2]) * t)
        desenho.line([(0, y), (largura, y)], fill=(r, g, b))
    return imagem


def _halo(imagem: Image.Image, cx: int, cy: int, raio: int, alpha_max: int) -> Image.Image:
    largura, altura = imagem.size
    halo = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(halo)
    for i in range(raio, 0, -6):
        alpha = int(alpha_max * (1 - i / raio))
        desenho.ellipse([cx - i, cy - i, cx + i, cy + i], fill=(*COR_ACCENT, alpha))
    return Image.alpha_composite(imagem.convert("RGBA"), halo).convert("RGB")


def _grao(imagem: Image.Image, intensidade: int = 6) -> Image.Image:
    largura, altura = imagem.size
    ruido = Image.effect_noise((largura, altura), 24).convert("L")
    ruido = ruido.point(lambda p: 128 + (p - 128) * intensidade // 24)
    ruido_rgb = Image.merge("RGB", (ruido, ruido, ruido))
    return Image.blend(imagem, ruido_rgb, 0.025)


def gerar_fundo_procedural(largura: int, altura: int, caminho: Path, semente: str = "") -> Path:
    rng = _seed_de(semente or f"{largura}x{altura}")
    imagem = _gradiente_base(largura, altura)

    cx = int(largura * rng.uniform(0.35, 0.65))
    cy = int(altura * rng.uniform(0.12, 0.22))
    imagem = _halo(imagem, cx, cy, int(min(largura, altura) * 0.6), 55)

    cx2 = int(largura * rng.uniform(0.1, 0.9))
    cy2 = int(altura * rng.uniform(0.55, 0.8))
    imagem = _halo(imagem, cx2, cy2, int(min(largura, altura) * 0.35), 22)

    imagem = _grao(imagem)
    imagem = imagem.filter(ImageFilter.GaussianBlur(0.6))
    imagem.save(caminho, "PNG")
    return caminho


# ---------------------------------------------------------------------------
# utilitários compartilhados por foto/ia
# ---------------------------------------------------------------------------

def _cobrir(imagem: Image.Image, largura: int, altura: int) -> Image.Image:
    """Redimensiona e corta a imagem pra preencher exatamente largura x altura (cover)."""
    proporcao_alvo = largura / altura
    proporcao_atual = imagem.width / imagem.height
    if proporcao_atual > proporcao_alvo:
        nova_altura = altura
        nova_largura = int(altura * proporcao_atual)
    else:
        nova_largura = largura
        nova_altura = int(largura / proporcao_atual)
    imagem = imagem.resize((nova_largura, nova_altura), Image.LANCZOS)
    esquerda = (nova_largura - largura) // 2
    topo = (nova_altura - altura) // 2
    return imagem.crop((esquerda, topo, esquerda + largura, topo + altura))


def _aplicar_overlay_legibilidade(imagem: Image.Image) -> Image.Image:
    """Escurece gradualmente a parte de baixo da foto — deixa a legenda legível
    e, de brinde, esconde marca d'água que esteja no canto inferior."""
    largura, altura = imagem.size
    overlay = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(overlay)
    inicio = int(altura * 0.5)
    for y in range(inicio, altura):
        t = (y - inicio) / max(altura - inicio - 1, 1)
        alpha = int(250 * t)
        desenho.line([(0, y), (largura, y)], fill=(*COR_FUNDO, alpha))
    return Image.alpha_composite(imagem.convert("RGBA"), overlay).convert("RGB")


# ---------------------------------------------------------------------------
# foto real — Openverse (sem chave) com Pexels como fonte extra (se configurado)
# ---------------------------------------------------------------------------

def _buscar_openverse(termo_busca: str) -> bytes | None:
    resposta = requests.get(
        OPENVERSE_URL,
        params={"q": termo_busca, "page_size": 1, "license_type": "commercial", "orientation": "landscape"},
        timeout=15,
    )
    if not resposta.ok:
        return None
    resultados = resposta.json().get("results") or []
    if not resultados:
        return None
    url_imagem = resultados[0].get("url") or resultados[0].get("thumbnail")
    if not url_imagem:
        return None
    imagem_resp = requests.get(url_imagem, timeout=20)
    if not imagem_resp.ok:
        return None
    return imagem_resp.content


def _buscar_pexels(termo_busca: str, orientacao: str) -> bytes | None:
    chave = os.environ.get("PEXELS_API_KEY")
    if not chave:
        return None
    resposta = requests.get(
        PEXELS_URL,
        headers={"Authorization": chave},
        params={"query": termo_busca, "per_page": 1, "orientation": orientacao},
        timeout=15,
    )
    if not resposta.ok:
        return None
    fotos = resposta.json().get("photos") or []
    if not fotos:
        return None
    imagem_resp = requests.get(fotos[0]["src"]["large2x"], timeout=20)
    if not imagem_resp.ok:
        return None
    return imagem_resp.content


def gerar_fundo_foto(largura: int, altura: int, caminho: Path, termo_busca: str) -> Path:
    """Busca uma foto real relacionada ao tema da cena. Tenta o Openverse primeiro
    (grátis, sem chave, agrega Flickr/Wikimedia/etc.); se não achar nada, tenta o
    Pexels (grátis, precisa de PEXELS_API_KEY — https://www.pexels.com/api/).
    Se a primeira foto achada for um close-up de rosto (comum em banco de imagens
    de "pessoa sorrindo pra câmera"), tenta a outra fonte antes de desistir."""
    orientacao = "portrait" if altura > largura else "landscape"

    candidatos_bytes = [b for b in (_buscar_openverse(termo_busca), _buscar_pexels(termo_busca, orientacao)) if b]
    if not candidatos_bytes:
        raise RuntimeError(
            f"Nenhuma foto encontrada para '{termo_busca}' (Openverse e Pexels). "
            "Configure PEXELS_API_KEY pra ter uma fonte extra."
        )

    candidatos = [Image.open(io.BytesIO(b)).convert("RGB") for b in candidatos_bytes]
    foto = next((c for c in candidatos if not _rosto_grande_demais(c)), candidatos[0])

    foto = _cobrir(foto, largura, altura)
    foto = _aplicar_overlay_legibilidade(foto)
    foto.save(caminho, "PNG")
    return caminho


# ---------------------------------------------------------------------------
# checagem de qualidade em foto real — rosto grande/de perto numa foto de banco
# de imagens costuma ser um clique de stock ruim pra fundo de vídeo. O detector
# do OpenCV funciona bem aqui (foto real é exatamente o que ele foi treinado
# pra reconhecer) — testei e ele NÃO funciona direito em desenho/ilustração
# (ver gerar_fundo_ia, que usa outra estratégia pra esse caso).
# ---------------------------------------------------------------------------

_DETECTOR_ROSTO = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
LIMIAR_AREA_ROSTO = 0.16  # rosto ocupando mais que isso da imagem = provável close-up de banco de imagens


def _rosto_grande_demais(imagem: Image.Image, limiar: float = LIMIAR_AREA_ROSTO) -> bool:
    cinza = cv2.cvtColor(np.array(imagem), cv2.COLOR_RGB2GRAY)
    rostos = _DETECTOR_ROSTO.detectMultiScale(cinza, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
    if len(rostos) == 0:
        return False
    area_imagem = imagem.width * imagem.height
    maior_rosto = max(w * h for (_, _, w, h) in rostos)
    return (maior_rosto / area_imagem) > limiar


# ---------------------------------------------------------------------------
# gerada por IA — Pollinations.ai (grátis, sem chave, sem cadastro)
# ---------------------------------------------------------------------------

def gerar_fundo_ia(
    largura: int,
    altura: int,
    caminho: Path,
    cena: str,
    semente: int | None = None,
    tentativas: int = 3,
    estilo_extra: str = "",
) -> Path:
    # Prompt curto: um texto de cena muito longo aumenta a chance de o serviço
    # gratuito (comunitário, às vezes instável) devolver erro.
    resumo_cena = _traduzir_para_ingles(cena.strip()[:200])[:200]
    resumo_cena = _evitar_gatilhos_de_rosto(resumo_cena)
    extra = f", {_traduzir_para_ingles(estilo_extra.strip()[:150])}" if estilo_extra.strip() else ""
    prompt = ESTILO_PROMPT_IA.format(cena=resumo_cena, extra=extra)
    url = POLLINATIONS_URL.format(prompt=urllib.parse.quote(prompt))
    params = {"width": largura, "height": altura, "nologo": "true"}
    if semente is not None:
        params["seed"] = semente

    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            resposta = requests.get(url, params=params, timeout=60)
            if resposta.ok:
                imagem = Image.open(io.BytesIO(resposta.content)).convert("RGB")
                imagem = _cobrir(imagem, largura, altura)
                imagem = _aplicar_overlay_legibilidade(imagem)
                imagem.save(caminho, "PNG")
                return caminho
            ultimo_erro = f"HTTP {resposta.status_code}"
        except requests.RequestException as erro:
            ultimo_erro = str(erro)
        time.sleep(2 * tentativa)

    raise RuntimeError(
        f"Pollinations.ai falhou {tentativas}x ({ultimo_erro}) pra cena: {resumo_cena[:60]}..."
    )


# ---------------------------------------------------------------------------
# dispatcher
# ---------------------------------------------------------------------------

def gerar_fundo(estilo: str, largura: int, altura: int, caminho: Path, cena: str, estilo_extra: str = "") -> Path:
    if estilo == "foto":
        return gerar_fundo_foto(largura, altura, caminho, termo_busca=cena)
    if estilo == "ia":
        return gerar_fundo_ia(largura, altura, caminho, cena=cena, estilo_extra=estilo_extra)
    return gerar_fundo_procedural(largura, altura, caminho, semente=cena)
