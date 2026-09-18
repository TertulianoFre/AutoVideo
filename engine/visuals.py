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
# O estilo pedido pelo usuário (descrição do vídeo) vem PRIMEIRO e o estilo
# padrão vem antes da cena: modelos pequenos dão mais peso ao começo do prompt,
# e palavras negativas ("no 3d") tendem a evocar justamente o que se quer evitar.
ESTILO_PROMPT_IA = (
    "{extra}flat 2d vector sticker illustration, simple cartoon shapes, thick outlines, "
    "solid flat colors, plain background, {cena}, wide shot, no text, no watermark"
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

def _buscar_openverse(termo_busca: str, assunto: str = "", excluir: set | None = None) -> tuple | None:
    """Devolve (bytes, url) de uma foto sorteada entre os melhores resultados.
    Com `assunto`, só aceita foto cujo título/tags mencionam o assunto (evita
    foto aleatória); `excluir` são URLs já usadas em outras cenas do vídeo."""
    import random

    excluir = excluir or set()
    resposta = requests.get(
        OPENVERSE_URL,
        params={"q": termo_busca, "page_size": 20, "license": "cc0,pdm"},
        timeout=15,
    )
    if not resposta.ok:
        return None
    resultados = resposta.json().get("results") or []
    palavras_assunto = [w.casefold() for w in assunto.split() if len(w) > 2]

    def relevante(r: dict) -> bool:
        if not palavras_assunto:
            return True
        texto = f'{r.get("title") or ""} ' + " ".join(tag.get("name", "") for tag in (r.get("tags") or []))
        return any(w in texto.casefold() for w in palavras_assunto)

    candidatos = [r for r in resultados if relevante(r) and (r.get("url") or r.get("thumbnail")) not in excluir]
    random.shuffle(candidatos)  # "gerar outra imagem" precisa poder trazer uma foto diferente
    for resultado in candidatos[:4]:
        url_imagem = resultado.get("url") or resultado.get("thumbnail")
        try:
            imagem_resp = requests.get(url_imagem, timeout=20)
        except requests.RequestException:
            continue
        if imagem_resp.ok:
            return imagem_resp.content, url_imagem
    return None


USER_AGENT = {"User-Agent": "ProjetoYT/1.0 (gerador local de videos; fotos de dominio publico)"}
WIKIMEDIA_URL = "https://commons.wikimedia.org/w/api.php"
NASA_URL = "https://images-api.nasa.gov"


def _mencionam_assunto(texto: str, assunto: str) -> bool:
    palavras = [w.casefold() for w in assunto.split() if len(w) > 2]
    return not palavras or any(w in texto.casefold() for w in palavras)


def _baixar(url: str) -> bytes | None:
    try:
        resposta = requests.get(url, headers=USER_AGENT, timeout=25)
    except requests.RequestException:
        return None
    return resposta.content if resposta.ok else None


def _buscar_wikimedia(termo_busca: str, assunto: str = "", excluir: set | None = None) -> tuple | None:
    """Wikimedia Commons: só arquivos em domínio público / CC0 (checado na licença de cada um)."""
    import random

    excluir = excluir or set()
    try:
        resposta = requests.get(
            WIKIMEDIA_URL,
            headers=USER_AGENT,
            params={
                "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                "gsrsearch": f"{termo_busca} filetype:bitmap", "gsrlimit": 30,
                "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1920,
            },
            timeout=15,
        )
    except requests.RequestException:
        return None
    if not resposta.ok:
        return None
    paginas = (resposta.json().get("query") or {}).get("pages") or {}
    candidatos = []
    for pagina in paginas.values():
        info = (pagina.get("imageinfo") or [{}])[0]
        licenca = ((info.get("extmetadata") or {}).get("LicenseShortName") or {}).get("value", "").casefold()
        livre = licenca.startswith(("public domain", "pd", "cc0", "cc-zero"))
        url = info.get("thumburl") or info.get("url")
        if (
            livre and url and url not in excluir and info.get("mime") in ("image/jpeg", "image/png")
            and (info.get("width") or 0) >= 1000 and _mencionam_assunto(pagina.get("title", ""), assunto)
        ):
            candidatos.append(url)
    random.shuffle(candidatos)
    for url in candidatos[:3]:
        conteudo = _baixar(url)
        if conteudo:
            return conteudo, url
    return None


def _buscar_nasa(termo_busca: str, assunto: str = "", excluir: set | None = None) -> tuple | None:
    """Biblioteca de imagens da NASA (domínio público) — ótima pra espaço."""
    import random

    excluir = excluir or set()
    try:
        resposta = requests.get(f"{NASA_URL}/search", headers=USER_AGENT, params={"q": termo_busca, "media_type": "image"}, timeout=15)
        if not resposta.ok:
            return None
        itens = (resposta.json().get("collection") or {}).get("items") or []
        itens = [
            i for i in itens
            if i.get("data") and _mencionam_assunto(i["data"][0].get("title") or "", assunto)
        ]
        random.shuffle(itens)
        for item in itens[:4]:
            nasa_id = item["data"][0].get("nasa_id")
            arquivos = requests.get(f"{NASA_URL}/asset/{nasa_id}", headers=USER_AGENT, timeout=15).json()["collection"]["items"]
            urls = [a["href"] for a in arquivos if a["href"].lower().endswith((".jpg", ".jpeg", ".png"))]
            url = next((u for u in urls if "~large" in u), None) or next((u for u in urls if "~medium" in u), None)
            if url and url not in excluir:
                conteudo = _baixar(url)
                if conteudo:
                    return conteudo, url
    except (requests.RequestException, KeyError, ValueError):
        return None
    return None


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


_PALAVRAS_GENERICAS = {
    "curiosidades", "curiosidade", "sobre", "porque", "por", "que", "como", "quando", "quais", "qual", "mais",
    "historia", "história", "fatos", "coisas", "incríveis", "incriveis", "melhores", "maiores", "nunca", "sempre",
}


def _assunto_do_video(contexto: str, pasta: Path) -> str:
    """Assunto principal do vídeo em inglês (1-2 palavras, ex: "octopus"). Uma
    chamada por vídeo, guardada em assunto_foto.txt — o serviço gratuito de IA
    limita chamadas seguidas, então não dá pra pedir de novo a cada cena."""
    import re
    import time
    from engine.roteiro import chamar_pollinations

    arquivo = pasta / "assunto_foto.txt"
    if arquivo.exists() and arquivo.read_text(encoding="utf-8").strip():
        return arquivo.read_text(encoding="utf-8").strip()
    for tentativa in range(3):
        try:
            texto = chamar_pollinations(
                [
                    {"role": "system", "content": "Responda SÓ com 1 ou 2 palavras em inglês: o assunto principal do vídeo, do jeito que se buscaria num banco de fotos (ex: octopus, Eiffel Tower, Saturn, pizza). Sem pontuação."},
                    {"role": "user", "content": contexto},
                ],
                2,
            )
            assunto = " ".join(re.sub(r"[^\w\s]", " ", texto).split()[:2])
            if assunto:
                arquivo.write_text(assunto, encoding="utf-8")
                return assunto
        except RuntimeError:
            time.sleep(4 * (tentativa + 1))
    # IA indisponível: usa as palavras "de peso" do próprio título (em português mesmo)
    palavras = [w for w in re.sub(r"[^\w\s]", " ", contexto).split() if len(w) > 3 and w.casefold() not in _PALAVRAS_GENERICAS]
    return " ".join(palavras[:2])


def _termos_de_busca(cena: str, contexto: str, pasta: Path) -> tuple:
    """A frase inteira da cena nunca acha nada num banco de fotos. Toda busca
    carrega o ASSUNTO do vídeo (a foto fica na mesma área) e, se a IA responder,
    palavras-chave da cena. Devolve (lista de buscas, assunto)."""
    import re
    from engine.roteiro import chamar_pollinations

    assunto = _assunto_do_video(contexto, pasta)
    chaves = ""
    try:
        texto = chamar_pollinations(
            [
                {"role": "system", "content": f"Responda SÓ com 1 a 3 palavras-chave em inglês, simples e comuns, pra buscar num banco de fotos uma imagem que ilustre o trecho. O assunto do vídeo é \"{assunto}\"; a foto deve ser sobre ele. Sem pontuação."},
                {"role": "user", "content": cena},
            ],
            1,
        )
        chaves = " ".join(re.sub(r"[^\w\s]", " ", texto).split()[:3])
    except RuntimeError:
        pass
    termos = []
    if assunto and chaves and chaves.casefold() != assunto.casefold():
        termos.append(f"{assunto} {chaves}")
    if assunto:
        termos.append(assunto)
    return termos, assunto


def gerar_fundo_foto(largura: int, altura: int, caminho: Path, termo_busca: str, contexto: str = "") -> Path:
    """Busca uma foto real relacionada ao tema da cena. Tenta o Openverse primeiro
    (grátis, sem chave, agrega Flickr/Wikimedia/etc.); se não achar nada, tenta o
    Pexels (grátis, precisa de PEXELS_API_KEY — https://www.pexels.com/api/).
    Se a primeira foto achada for um close-up de rosto (comum em banco de imagens
    de "pessoa sorrindo pra câmera"), tenta a outra fonte antes de desistir."""
    orientacao = "portrait" if altura > largura else "landscape"

    # fotos já usadas em qualquer cena desse vídeo (inclusive a que está sendo
    # trocada) não entram de novo — o arquivo .fonte guarda a URL de cada uma
    usadas = set()
    for arquivo in caminho.parent.glob("cena*.fonte"):
        usadas.add(arquivo.read_text(encoding="utf-8").strip())

    termos, assunto = _termos_de_busca(termo_busca, contexto, caminho.parent)
    candidatos = []  # (bytes, url)
    for termo in termos:
        for buscador in (_buscar_openverse, _buscar_wikimedia, _buscar_nasa):
            try:
                achou = buscador(termo, assunto, usadas)
            except requests.RequestException:
                achou = None
            if achou:
                candidatos.append(achou)
        pexels = _buscar_pexels(termo, orientacao)
        if pexels:
            candidatos.append((pexels, None))
        if candidatos:
            break
    import random
    random.shuffle(candidatos)  # varia a fonte entre cenas
    if not candidatos:
        raise RuntimeError(
            f"Nenhuma foto livre (domínio público) encontrada para '{assunto or termo_busca}' (Openverse e Pexels). "
            "Configure PEXELS_API_KEY pra ter uma fonte extra."
        )

    imagens = [(Image.open(io.BytesIO(b)).convert("RGB"), url) for b, url in candidatos]
    foto, url_escolhida = next(((im, u) for im, u in imagens if not _rosto_grande_demais(im)), imagens[0])
    if url_escolhida:
        caminho.with_suffix(".fonte").write_text(url_escolhida, encoding="utf-8")

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
    extra = f"{_traduzir_para_ingles(estilo_extra.strip()[:150])}, " if estilo_extra.strip() else ""
    prompt = ESTILO_PROMPT_IA.format(cena=resumo_cena, extra=extra)
    url = POLLINATIONS_URL.format(prompt=urllib.parse.quote(prompt))
    # a IA compõe o assunto espremido/alongado em quadros muito altos: pede
    # quadrado (proporção natural) e o corte central pro vertical é feito depois
    if altura > largura:
        params = {"width": 1024, "height": 1024, "nologo": "true"}
    else:
        params = {"width": 1024, "height": 576, "nologo": "true"}
    if semente is not None:
        params["seed"] = semente

    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            resposta = requests.get(url, params=params, timeout=60)
            if resposta.ok:
                imagem = Image.open(io.BytesIO(resposta.content)).convert("RGB")
                # o serviço gratuito devolve ~1024px com marca d'água no canto inferior:
                # corta a faixa de baixo antes de esticar pro tamanho final
                imagem = imagem.crop((0, 0, imagem.width, int(imagem.height * 0.95)))
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

def gerar_fundo(estilo: str, largura: int, altura: int, caminho: Path, cena: str, estilo_extra: str = "", contexto: str = "") -> Path:
    if estilo == "foto":
        return gerar_fundo_foto(largura, altura, caminho, termo_busca=cena, contexto=contexto)
    if estilo == "ia":
        return gerar_fundo_ia(largura, altura, caminho, cena=cena, estilo_extra=estilo_extra)
    return gerar_fundo_procedural(largura, altura, caminho, semente=cena)
