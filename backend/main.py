"""Backend do app: serve a tela e a API que aciona o motor de geração.

Rodar: .venv\\Scripts\\uvicorn backend.main:app --reload
"""

import io
import json
import random
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# O texto gerado por IA às vezes traz pontuação Unicode especial (hífen
# não-quebrável, travessão...) que quebra o print() no console do Windows
# (codepage padrão não sabe codificar) — evita que um log derrube o servidor.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from backend import jobs
from engine import afiliados, agendador, agente, biblioteca, canal, roteiro as roteiro_mod
from engine import thumbnail as thumbnail_mod
from engine import tts as tts_mod
from engine import youtube as youtube_mod
from engine.pipeline import RAIZ_SAIDA, slug_titulo

RAIZ = Path(__file__).resolve().parent.parent
FRONTEND = RAIZ / "frontend"

RAIZ_SAIDA.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Projeto YT")

# roda junto com o app inteiro: confere de tempos em tempos se algum vídeo
# tem data de postagem vencida e publica sozinho no YouTube (cada um na conta
# do canal dele — engine.agendador resolve isso por vídeo).
agendador.iniciar_agendador()

# status de conexão do YouTube é por canal (dois canais podem estar
# conectando ao mesmo tempo, em tese) — chave é o canal_id.
_estado_conexao_youtube: dict[str, dict] = {}


def _estado_de(canal_id: str) -> dict:
    return _estado_conexao_youtube.setdefault(canal_id, {"status": "ocioso", "erro": None})


biblioteca.PASTA_AUDIOS.mkdir(parents=True, exist_ok=True)
biblioteca.PASTA_IMAGENS.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")
app.mount("/videos", StaticFiles(directory=RAIZ_SAIDA), name="videos")
app.mount("/biblioteca", StaticFiles(directory=biblioteca.RAIZ), name="biblioteca")


@app.get("/", response_class=HTMLResponse)
def pagina_inicial() -> str:
    return (FRONTEND / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# canais: cada um tem nome, contexto (nicho/tom/público) e conta do YouTube
# própria. Um fica "ativo" por vez — é o que Novo Vídeo/Agente usam; a Fila
# mostra vídeos de todos os canais.
# ---------------------------------------------------------------------------

@app.get("/api/canais")
def api_listar_canais() -> dict:
    return {"canais": canal.listar_canais(), "ativo": canal.canal_ativo_id()}


@app.post("/api/canais")
def api_criar_canal(nome: str = Form(...), contexto: str = Form("")) -> dict:
    try:
        novo = canal.criar_canal(nome, contexto)
    except ValueError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=400)
    return {"canal": novo}


@app.post("/api/canais/{canal_id}/ativar")
def api_ativar_canal(canal_id: str) -> dict:
    try:
        canal.definir_ativo(canal_id)
    except ValueError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=404)
    return {"ok": True}


@app.post("/api/canais/{canal_id}/editar")
def api_editar_canal(canal_id: str, nome: str = Form(""), contexto: str = Form(""), conta_youtube: str = Form("")) -> dict:
    try:
        atualizado = canal.atualizar_canal(canal_id, nome=nome or None, contexto=contexto, conta_youtube=conta_youtube or None)
    except ValueError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=404)
    return {"canal": atualizado}


# ---------------------------------------------------------------------------
# conexão com o YouTube (publicação automática) — uma conta por canal
# ---------------------------------------------------------------------------

def _conta_do_canal(canal_id: str | None) -> str:
    info = canal.obter_canal(canal_id or canal.canal_ativo_id())
    return info["conta_youtube"] if info else canal.CANAL_PADRAO_ID


@app.get("/api/youtube/status")
def api_youtube_status(canal_id: str | None = None) -> dict:
    conta = _conta_do_canal(canal_id)
    estado = _estado_de(conta)
    return {
        "conectado": youtube_mod.esta_conectado(conta),
        "conectando": estado["status"] == "conectando",
        "erro": estado["erro"],
        "client_secret_presente": youtube_mod.CLIENT_SECRET_PATH.exists(),
    }


@app.post("/api/youtube/conectar")
def api_youtube_conectar(canal_id: str | None = Form(None)) -> dict:
    conta = _conta_do_canal(canal_id)
    estado = _estado_de(conta)
    if estado["status"] == "conectando":
        return {"status": "conectando"}

    estado["status"] = "conectando"
    estado["erro"] = None

    def rodar() -> None:
        try:
            youtube_mod.conectar(conta)
            estado["status"] = "conectado"
        except Exception as erro:
            estado["status"] = "erro"
            estado["erro"] = str(erro)

    # abre o navegador padrão do sistema e espera você autorizar — não pode
    # rodar na thread principal, ia travar o servidor até você terminar.
    threading.Thread(target=rodar, daemon=True).start()
    return {"status": "conectando"}


@app.get("/api/youtube/estatisticas")
def api_youtube_estatisticas(canal_id: str | None = None) -> JSONResponse:
    try:
        return JSONResponse(youtube_mod.obter_estatisticas_canal(_conta_do_canal(canal_id)))
    except Exception as erro:
        # inclui HttpError da API do Google (ex: token sem o escopo readonly
        # ainda, porque foi conectado antes desse escopo existir).
        return JSONResponse({"erro": str(erro)}, status_code=409)


@app.get("/api/youtube/serie")
def api_youtube_serie(dias: int = 28, canal_id: str | None = None) -> JSONResponse:
    dias = max(7, min(dias, 90))
    conta = _conta_do_canal(canal_id)
    try:
        serie = youtube_mod.obter_serie_diaria(conta, dias)
        atual = youtube_mod.obter_estatisticas_canal(conta)["inscritos"]
    except Exception as erro:
        return JSONResponse({"erro": str(erro)}, status_code=409)
    return JSONResponse({"serie": serie, "inscritos_atual": atual})


# ---------------------------------------------------------------------------
# agente: sugere ideias de vídeo (opcionalmente inspirado em tendências)
# ---------------------------------------------------------------------------

@app.post("/api/agente/sugestoes")
def api_agente_sugestoes() -> JSONResponse:
    """Sempre sobre o canal ATIVO — é ele que define o contexto e a conta do
    YouTube usados pra puxar tendências."""
    conta = _conta_do_canal(None)
    tendencias = []
    aviso_tendencias = None
    if youtube_mod.esta_conectado(conta):
        try:
            tendencias = youtube_mod.obter_tendencias(conta)
        except Exception as erro:
            aviso_tendencias = f"Não consegui buscar tendências ({erro}) — sugestões vão sair sem esse contexto."
    else:
        aviso_tendencias = "Conecte o YouTube (na aba Canais) pra sugestões levarem em conta o que está em alta."

    try:
        ideias = agente.sugerir_ideias(canal.obter_contexto(), tendencias)
    except RuntimeError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=502)

    return JSONResponse({"ideias": ideias, "aviso": aviso_tendencias})


_RE_DATA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_RE_HORA = re.compile(r"\d{2}:\d{2}")


@app.post("/api/agente/perguntar")
def api_agente_perguntar(mensagem: str = Form(...)) -> JSONResponse:
    """Campo livre do agente: responde perguntas/pede ideias, ou executa um
    comando simples reconhecido (por enquanto só reagendar um vídeo). Toda
    ação vinda do modelo é validada contra o estado real antes de aplicar —
    nunca confia cegamente no que ele disser."""
    mensagem = mensagem.strip()
    if not mensagem:
        return JSONResponse({"erro": "escreve alguma coisa pro agente"}, status_code=400)

    videos = api_listar_videos()
    try:
        resultado = agente.responder_livre(mensagem, canal.obter_contexto(), videos)
    except RuntimeError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=502)

    if resultado.get("acao") != "reagendar":
        return JSONResponse({"acao": "responder", "resposta": resultado.get("texto", "")})

    slug = str(resultado.get("slug") or "")
    data_postagem = str(resultado.get("data_postagem") or "")
    hora_postagem = resultado.get("hora_postagem")
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"

    if not slug or not caminho_meta.exists():
        return JSONResponse({"acao": "erro", "resposta": f'Não achei nenhum vídeo "{slug}" pra reagendar — confira o título e tente de novo.'})
    if not _RE_DATA_ISO.fullmatch(data_postagem):
        return JSONResponse({"acao": "erro", "resposta": "Não entendi pra qual data reagendar — pode repetir com uma data mais clara?"})
    if hora_postagem and not _RE_HORA.fullmatch(str(hora_postagem)):
        hora_postagem = None

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    metadados["data_postagem"] = data_postagem
    if hora_postagem:
        metadados["hora_postagem"] = hora_postagem
    else:
        metadados.pop("hora_postagem", None)
    caminho_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")

    return JSONResponse(
        {
            "acao": "reagendar",
            "resposta": resultado.get("texto") or f"Reagendado \"{metadados.get('titulo', slug)}\" pra {data_postagem}.",
            "slug": slug,
            "data_postagem": data_postagem,
            "hora_postagem": hora_postagem,
        }
    )


# ---------------------------------------------------------------------------
# biblioteca: áudios e imagens importados por você, reutilizáveis em qualquer vídeo
# ---------------------------------------------------------------------------

TAMANHO_MAX_BIBLIOTECA_BYTES = 40 * 1024 * 1024


@app.get("/api/biblioteca")
def api_listar_biblioteca() -> dict:
    return {
        "audios": [f"/biblioteca/audios/{nome}" for nome in biblioteca.listar_audios()],
        "audios_nomes": biblioteca.listar_audios(),
        "imagens": [{"nome": nome, "url": f"/biblioteca/imagens/{nome}"} for nome in biblioteca.listar_imagens()],
    }


@app.post("/api/biblioteca/audios/upload")
async def api_upload_audio_biblioteca(arquivo: UploadFile = File(...)) -> JSONResponse:
    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAX_BIBLIOTECA_BYTES:
        return JSONResponse({"erro": "arquivo maior que 40MB"}, status_code=400)
    try:
        nome = biblioteca.salvar_audio(arquivo.filename or "audio", conteudo)
    except ValueError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=400)
    return JSONResponse({"nome": nome, "url": f"/biblioteca/audios/{nome}"})


@app.delete("/api/biblioteca/audios/{nome}")
def api_remover_audio_biblioteca(nome: str) -> JSONResponse:
    if not biblioteca.remover_audio(Path(nome).name):
        return JSONResponse({"erro": "áudio não encontrado"}, status_code=404)
    return JSONResponse({"ok": True})


@app.post("/api/biblioteca/imagens/upload")
async def api_upload_imagem_biblioteca(arquivo: UploadFile = File(...)) -> JSONResponse:
    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAX_BIBLIOTECA_BYTES:
        return JSONResponse({"erro": "arquivo maior que 40MB"}, status_code=400)
    try:
        nome = biblioteca.salvar_imagem(arquivo.filename or "imagem", conteudo)
    except Exception:
        return JSONResponse({"erro": "não consegui abrir esse arquivo como imagem"}, status_code=400)
    return JSONResponse({"nome": nome, "url": f"/biblioteca/imagens/{nome}"})


@app.delete("/api/biblioteca/imagens/{nome}")
def api_remover_imagem_biblioteca(nome: str) -> JSONResponse:
    if not biblioteca.remover_imagem(Path(nome).name):
        return JSONResponse({"erro": "imagem não encontrada"}, status_code=404)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# afiliados: lista de produtos/links pra divulgar (ideia guardada, ainda sem
# inserção automática nos vídeos)
# ---------------------------------------------------------------------------

@app.get("/api/afiliados")
def api_listar_afiliados() -> list[dict]:
    return afiliados.listar()


@app.post("/api/afiliados")
def api_adicionar_afiliado(
    nome: str = Form(...),
    plataforma: str = Form("outro"),
    link: str = Form(""),
    nota: str = Form(""),
) -> JSONResponse:
    nome = nome.strip()
    if not nome:
        return JSONResponse({"erro": "dê um nome pro produto"}, status_code=400)
    item = afiliados.adicionar(nome, plataforma, link, nota)
    return JSONResponse(item)


@app.delete("/api/afiliados/{item_id}")
def api_remover_afiliado(item_id: str) -> JSONResponse:
    if not afiliados.remover(item_id):
        return JSONResponse({"erro": "não encontrado"}, status_code=404)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# pré-visualização do roteiro (antes de gerar o vídeo inteiro)
# ---------------------------------------------------------------------------

@app.post("/api/roteiro/preview")
def api_preview_roteiro(
    titulo: str = Form(...),
    duracao_alvo: float | None = Form(None),
    descricao_video: str = Form(""),
) -> JSONResponse:
    try:
        roteiro = roteiro_mod.gerar_roteiro(
            titulo.strip(),
            duracao_alvo or 1.0,
            contexto_canal=canal.obter_contexto(),
            descricao_video=descricao_video.strip(),
        )
        return JSONResponse({"roteiro": roteiro})
    except RuntimeError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=502)


# ---------------------------------------------------------------------------
# geração de vídeo
# ---------------------------------------------------------------------------

@app.post("/api/videos")
def api_criar_video(
    titulo: str = Form(...),
    data_postagem: str = Form(...),
    hora_postagem: str = Form(""),
    roteiro: str = Form(""),
    descricao_video: str = Form(""),
    idioma: str = Form("pt-BR"),
    voz: str = Form("mulher"),
    imagem: str = Form("procedural"),
    duracao_alvo: float | None = Form(None),
    sem_narracao: bool = Form(False),
    som_fundo_tipo: str = Form(""),
    som_fundo_descricao: str = Form(""),
    som_fundo_biblioteca: str = Form(""),
    privacidade: str = Form("public"),
    narracao_audio: UploadFile | None = File(None),
) -> dict:
    titulo = titulo.strip()
    if privacidade not in ("private", "unlisted", "public"):
        privacidade = "public"
    roteiro_limpo = roteiro.strip()
    narracao_customizada = False

    if narracao_audio is not None and narracao_audio.filename and not sem_narracao:
        if not roteiro_limpo:
            return JSONResponse(
                {"erro": "com narração gravada/enviada, cole no campo Roteiro exatamente o texto que você leu antes de enviar"},
                status_code=400,
            )
        conteudo = narracao_audio.file.read()
        if len(conteudo) > TAMANHO_MAX_BIBLIOTECA_BYTES:
            return JSONResponse({"erro": "áudio de narração maior que 40MB"}, status_code=400)
        pasta = RAIZ_SAIDA / slug_titulo(titulo)
        pasta.mkdir(parents=True, exist_ok=True)
        try:
            tts_mod.salvar_narracao_customizada(conteudo, pasta / "narracao_custom.mp3")
        except ValueError as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400)
        narracao_customizada = True

    params = dict(
        titulo=titulo,
        roteiro=None if sem_narracao else (roteiro_limpo or None),
        idioma=idioma,
        voz=voz,
        estilo_imagem=imagem,
        duracao_alvo_minutos=duracao_alvo,
        descricao_video=descricao_video.strip(),
        data_postagem=data_postagem,
        hora_postagem=hora_postagem.strip() or None,
        sem_narracao=sem_narracao,
        som_fundo_tipo=som_fundo_tipo,
        som_fundo_descricao=som_fundo_descricao.strip(),
        som_fundo_biblioteca=som_fundo_biblioteca.strip(),
        narracao_customizada=narracao_customizada,
        privacidade=privacidade,
        canal_id=canal.canal_ativo_id(),  # vídeo pertence ao canal ativo no momento em que foi criado
    )

    job = jobs.criar_job(titulo, params)
    return {"job_id": job.id}


@app.post("/api/videos/{slug}/regenerar")
def api_regenerar_video(slug: str, manter_roteiro: bool = Form(True)) -> dict:
    """Gera tudo de novo — narração, imagens, montagem. Por padrão mantém o
    roteiro já existente (o problema geralmente é imagem, não texto); passe
    manter_roteiro=false pra escrever um roteiro novo também."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    titulo = metadados.get("titulo", slug)
    sem_narracao = metadados.get("sem_narracao", False)

    roteiro_existente = None
    caminho_roteiro = pasta / "roteiro.txt"
    if manter_roteiro and not sem_narracao and caminho_roteiro.exists():
        roteiro_existente = caminho_roteiro.read_text(encoding="utf-8")

    params = dict(
        titulo=titulo,
        roteiro=roteiro_existente,
        idioma=metadados.get("idioma", "pt-BR"),
        voz=metadados.get("voz", "mulher"),
        estilo_imagem=metadados.get("estilo_imagem", "procedural"),
        duracao_alvo_minutos=metadados.get("duracao_alvo_minutos") or (15.0 if sem_narracao else 1.0),
        descricao_video=metadados.get("descricao_video", ""),
        data_postagem=metadados.get("data_postagem"),
        hora_postagem=metadados.get("hora_postagem"),
        sem_narracao=sem_narracao,
        som_fundo_tipo=metadados.get("som_fundo_tipo", ""),
        som_fundo_descricao=metadados.get("som_fundo_descricao", ""),
        som_fundo_biblioteca=metadados.get("som_fundo_biblioteca", ""),
        narracao_customizada=metadados.get("narracao_customizada", False),
        privacidade=metadados.get("privacidade", "public"),
        canal_id=metadados.get("canal_id"),  # mantém o canal original do vídeo, não o ativo agora
    )

    job = jobs.criar_job(titulo, params)
    return {"job_id": job.id}


@app.post("/api/videos/{slug}/agendamento")
def api_editar_agendamento(slug: str, data_postagem: str = Form(...), hora_postagem: str = Form("")) -> dict:
    """Só reagenda (data/hora de postagem) sem regenerar nada — pra corrigir
    rapidinho quando o plano de publicação muda."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    metadados["data_postagem"] = data_postagem
    if hora_postagem.strip():
        metadados["hora_postagem"] = hora_postagem.strip()
    else:
        metadados.pop("hora_postagem", None)
    caminho_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "data_postagem": data_postagem, "hora_postagem": metadados.get("hora_postagem")}


def _thumbnail_base_url(pasta: Path) -> str | None:
    """URL da imagem de cena usada como fundo da thumbnail atual (sem o
    texto/overlay desenhado) — usada pra arrastar o texto em cima dela."""
    fonte_txt = pasta / "thumbnail_fonte.txt"
    nome = fonte_txt.read_text(encoding="utf-8").strip() if fonte_txt.exists() else "cena00_16x9.png"
    caminho = pasta / nome
    if not caminho.exists():
        candidatas = sorted(pasta.glob("cena*_16x9.png"))
        if not candidatas:
            return None
        caminho = candidatas[0]
    return f"/videos/{pasta.name}/{caminho.name}?v={int(caminho.stat().st_mtime)}"


def _pos_livre_de(metadados: dict) -> tuple | None:
    """(fracao_x, fracao_y) salvos de um arraste, ou None se a thumbnail usa a
    grade de 9 pontos (thumbnail_posicao) — arrastar sempre tem prioridade
    sobre a grade quando os dois estão salvos."""
    x, y = metadados.get("thumbnail_pos_x"), metadados.get("thumbnail_pos_y")
    return (x, y) if isinstance(x, (int, float)) and isinstance(y, (int, float)) else None


def _tamanho_fonte_de(metadados: dict) -> int:
    """Tamanho em pixels: usa o valor livre salvo (thumbnail_tamanho_px, do
    controle deslizante) se existir; senão cai pro preset antigo
    (pequeno/médio/grande) de thumbnails salvas antes desse controle existir."""
    px = metadados.get("thumbnail_tamanho_px")
    if isinstance(px, (int, float)) and px:
        return int(px)
    return thumbnail_mod.TAMANHOS.get(metadados.get("thumbnail_tamanho", "medio"), 80)


def _status_de(metadados: dict) -> str:
    """Status resumido pra fila: publicado / erro / pronto (dia já chegou,
    esperando o agendador ou o próximo publicar manual) / aguardando (ainda
    não chegou a data)."""
    if metadados.get("publicado"):
        return "publicado"
    if metadados.get("publicacao_erro"):
        return "erro"
    data_postagem = metadados.get("data_postagem")
    if not data_postagem:
        return "aguardando"
    agora = datetime.now()
    hoje = agora.date().isoformat()
    if data_postagem > hoje:
        return "aguardando"
    hora_postagem = metadados.get("hora_postagem")
    if data_postagem == hoje and hora_postagem and agora.strftime("%H:%M") < hora_postagem:
        return "aguardando"
    return "pronto"


def _base_valida_ou_erro(pasta: Path) -> Path | JSONResponse:
    """Imagem de cena/custom atualmente usada como base, ou um erro se a
    pasta não tiver nenhuma."""
    fonte_txt = pasta / "thumbnail_fonte.txt"
    fonte_nome = fonte_txt.read_text(encoding="utf-8").strip() if fonte_txt.exists() else "cena00_16x9.png"
    base = pasta / fonte_nome
    if base.exists():
        return base
    candidatas = sorted(pasta.glob("cena*_16x9.png"))
    if not candidatas:
        return JSONResponse({"erro": "não achei nenhuma imagem de cena pra usar de base"}, status_code=404)
    return candidatas[0]


def _rerenderizar_thumbnail(pasta: Path, base: Path, metadados: dict) -> None:
    texto = metadados.get("thumbnail_texto") or metadados.get("titulo", pasta.name)
    cor = thumbnail_mod.cor_de_hex(metadados.get("thumbnail_cor", ""))
    posicao = metadados.get("thumbnail_posicao", "baixo-centro")
    thumbnail_mod.gerar_thumbnail(base, texto, pasta / "thumbnail.png", cor, posicao, _tamanho_fonte_de(metadados), _pos_livre_de(metadados))


@app.post("/api/videos/{slug}/thumbnail/regenerar")
def api_regenerar_thumbnail(slug: str) -> dict:
    """Refaz só a thumbnail (rápido, não mexe no vídeo) — sorteia uma imagem
    de cena diferente da atual como base, pra você poder ficar pedindo outra
    até gostar."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    candidatas = sorted(pasta.glob("cena*_16x9.png"))
    if not candidatas:
        return JSONResponse({"erro": "não achei nenhuma imagem de cena pra usar de base"}, status_code=404)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))

    atual = pasta / "thumbnail_fonte.txt"
    fonte_anterior = atual.read_text(encoding="utf-8").strip() if atual.exists() else None
    opcoes = [c for c in candidatas if c.name != fonte_anterior] or candidatas
    escolhida = random.choice(opcoes)

    _rerenderizar_thumbnail(pasta, escolhida, metadados)
    atual.write_text(escolhida.name, encoding="utf-8")

    return {"thumbnail": f"/videos/{slug}/thumbnail.png?v={int(time.time())}", "thumbnail_base": _thumbnail_base_url(pasta)}


@app.get("/api/videos/{slug}/thumbnail/imagens")
def api_listar_imagens_thumbnail(slug: str) -> dict:
    """Todas as imagens de cena (+ a customizada enviada, se houver) que dá
    pra escolher como base da thumbnail, pra mostrar uma galeria pra clicar
    em vez de só sortear aleatoriamente."""
    pasta = RAIZ_SAIDA / slug
    if not pasta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    fonte_txt = pasta / "thumbnail_fonte.txt"
    atual = fonte_txt.read_text(encoding="utf-8").strip() if fonte_txt.exists() else "cena00_16x9.png"

    candidatas = sorted(pasta.glob("cena*_16x9.png"))
    custom = pasta / "thumbnail_custom.png"
    if custom.exists():
        candidatas.append(custom)

    imagens = [
        {"nome": c.name, "url": f"/videos/{slug}/{c.name}?v={int(c.stat().st_mtime)}", "atual": c.name == atual}
        for c in candidatas
    ]
    # imagens importadas na Base também podem virar fundo de thumbnail —
    # identificadas com o prefixo "biblioteca:" pra distinguir de cenas locais
    imagens += [
        {"nome": f"biblioteca:{nome}", "url": f"/biblioteca/imagens/{nome}", "atual": f"biblioteca-{nome}" == atual}
        for nome in biblioteca.listar_imagens()
    ]
    return {"imagens": imagens}


@app.post("/api/videos/{slug}/thumbnail/escolher-imagem")
def api_escolher_imagem_thumbnail(slug: str, imagem: str = Form(...)) -> dict:
    """Troca a imagem de base da thumbnail pra uma cena específica (em vez de
    sortear) ou pra imagem customizada já enviada."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    if imagem.startswith("biblioteca:"):
        # imagem da Base: valida contra o que existe de verdade na biblioteca
        # (nunca um caminho arbitrário) e copia pra dentro da pasta do vídeo,
        # assim o resto do fluxo (thumbnail_fonte.txt etc.) funciona igual
        origem = biblioteca.caminho_imagem_valida(imagem[len("biblioteca:"):])
        if origem is None:
            return JSONResponse({"erro": "imagem inválida"}, status_code=400)
        nome = f"biblioteca-{origem.name}"
        shutil.copyfile(origem, pasta / nome)
    else:
        # só aceita nomes que já existem de verdade na pasta do vídeo (cena*_16x9.png
        # ou a customizada) — nunca um caminho arbitrário vindo do cliente
        nome = Path(imagem).name
        validos = {c.name for c in pasta.glob("cena*_16x9.png")}
        custom = pasta / "thumbnail_custom.png"
        if custom.exists():
            validos.add(custom.name)
        if nome not in validos:
            return JSONResponse({"erro": "imagem inválida"}, status_code=400)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    _rerenderizar_thumbnail(pasta, pasta / nome, metadados)
    (pasta / "thumbnail_fonte.txt").write_text(nome, encoding="utf-8")

    return {"thumbnail": f"/videos/{slug}/thumbnail.png?v={int(time.time())}", "thumbnail_base": _thumbnail_base_url(pasta)}


TAMANHO_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB, só sanidade


@app.post("/api/videos/{slug}/thumbnail/upload")
async def api_upload_imagem_thumbnail(slug: str, arquivo: UploadFile = File(...)) -> dict:
    """Sobe uma imagem sua (ex: uma foto real, um design pronto) pra usar
    como base da thumbnail, no lugar de uma cena gerada."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAX_UPLOAD_BYTES:
        return JSONResponse({"erro": "arquivo maior que 20MB"}, status_code=400)

    try:
        imagem = Image.open(io.BytesIO(conteudo))
        imagem.load()  # decodifica agora — detecta arquivo corrompido ou que não é imagem de verdade
        imagem = imagem.convert("RGB")
    except Exception:
        return JSONResponse({"erro": "não consegui abrir esse arquivo como imagem"}, status_code=400)

    caminho_base = pasta / "thumbnail_custom.png"
    imagem.save(caminho_base, "PNG")

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    _rerenderizar_thumbnail(pasta, caminho_base, metadados)
    (pasta / "thumbnail_fonte.txt").write_text(caminho_base.name, encoding="utf-8")

    return {"thumbnail": f"/videos/{slug}/thumbnail.png?v={int(time.time())}", "thumbnail_base": _thumbnail_base_url(pasta)}


@app.post("/api/videos/{slug}/thumbnail/editar")
def api_editar_thumbnail(
    slug: str,
    texto: str = Form(...),
    cor: str = Form(""),
    posicao: str = Form("baixo-centro"),
    tamanho_px: int = Form(80),
    pos_x: float | None = Form(None),
    pos_y: float | None = Form(None),
) -> dict:
    """Troca o texto, a cor, o tamanho (em pixels, controle deslizante) e a
    posição da thumbnail (grade de 9 pontos OU arrastar livre — se pos_x/pos_y
    vierem preenchidos, arrastar manda e some com a grade), mantendo a mesma
    imagem de base atual. Fica salvo pro vídeo (sobrevive a "nova thumbnail" e
    a regenerar a cena 0) até você editar de novo."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    texto = texto.strip()
    if not texto:
        return JSONResponse({"erro": "o texto da thumbnail não pode ficar vazio"}, status_code=400)

    base = _base_valida_ou_erro(pasta)
    if isinstance(base, JSONResponse):
        return base

    cor_rgb = thumbnail_mod.cor_de_hex(cor)
    posicao = posicao if posicao in thumbnail_mod.POSICOES else "baixo-centro"
    tamanho_px = max(thumbnail_mod.TAMANHO_FONTE_MIN, min(thumbnail_mod.TAMANHO_FONTE_MAX, tamanho_px))
    pos_livre = (pos_x, pos_y) if pos_x is not None and pos_y is not None else None
    thumbnail_mod.gerar_thumbnail(base, texto, pasta / "thumbnail.png", cor_rgb, posicao, tamanho_px, pos_livre)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    metadados["thumbnail_texto"] = texto
    metadados["thumbnail_cor"] = cor.strip().lstrip("#") if cor_rgb else ""
    metadados["thumbnail_posicao"] = posicao
    if pos_livre is not None:
        metadados["thumbnail_pos_x"], metadados["thumbnail_pos_y"] = pos_livre
    else:
        metadados.pop("thumbnail_pos_x", None)
        metadados.pop("thumbnail_pos_y", None)
    metadados["thumbnail_tamanho_px"] = tamanho_px
    metadados.pop("thumbnail_tamanho", None)
    caminho_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"thumbnail": f"/videos/{slug}/thumbnail.png?v={int(time.time())}"}


@app.get("/api/videos/{slug}/cenas")
def api_listar_cenas(slug: str) -> dict:
    """Lista as cenas do vídeo (texto + imagem de cada uma) pra edição pontual."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    cenas = metadados.get("cenas")
    if not cenas:
        return JSONResponse(
            {"erro": 'Esse vídeo foi gerado antes desse recurso existir — clique em "Regenerar" uma vez pra habilitar.'},
            status_code=409,
        )

    resultado = []
    for i, cena in enumerate(cenas):
        caminho_imagem = pasta / f"cena{i:02d}_16x9.png"
        resultado.append(
            {
                "indice": i,
                "texto": cena.get("texto", ""),
                "duracao_segundos": cena.get("duracao_segundos", 0),
                "imagem": f"/videos/{slug}/cena{i:02d}_16x9.png?v={int(caminho_imagem.stat().st_mtime)}" if caminho_imagem.exists() else None,
            }
        )
    return {"cenas": resultado}


@app.post("/api/videos/{slug}/cenas/{indice}/regenerar")
def api_regenerar_cena(slug: str, indice: int) -> dict:
    """Refaz só a imagem de uma cena e remonta o vídeo — não mexe em roteiro,
    narração nem nas outras cenas."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    titulo = metadados.get("titulo", slug)

    job = jobs.criar_job_cena(titulo, slug, indice)
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def api_status_job(job_id: str) -> JSONResponse:
    job = jobs.obter_job(job_id)
    if job is None:
        return JSONResponse({"erro": "job não encontrado"}, status_code=404)
    return JSONResponse(
        {
            "status": job.status,
            "etapa": job.etapa,
            "progresso": job.progresso,
            "resultado": job.resultado,
            "erro": job.erro,
        }
    )


@app.get("/api/videos")
def api_listar_videos() -> list[dict]:
    if not RAIZ_SAIDA.exists():
        return []
    pastas = [p for p in RAIZ_SAIDA.iterdir() if p.is_dir()]
    pastas.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    videos = []
    for pasta in pastas:
        v16, v9 = pasta / "video_16x9.mp4", pasta / "video_9x16.mp4"
        if not (v16.exists() and v9.exists()):
            continue

        metadados = {}
        caminho_meta = pasta / "metadata.json"
        if caminho_meta.exists():
            metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))

        tags_path = pasta / "tags.txt"
        tags = tags_path.read_text(encoding="utf-8") if tags_path.exists() else ""
        thumb_path = pasta / "thumbnail.png"

        canal_id_video = metadados.get("canal_id") or canal.CANAL_PADRAO_ID
        canal_info = canal.obter_canal(canal_id_video)

        videos.append(
            {
                "slug": pasta.name,
                "titulo": metadados.get("titulo") or pasta.name.replace("-", " "),
                "canal_id": canal_id_video,
                "canal_nome": canal_info["nome"] if canal_info else canal_id_video,
                "sem_narracao": metadados.get("sem_narracao", False),
                "som_fundo_tipo": metadados.get("som_fundo_tipo", ""),
                "data_postagem": metadados.get("data_postagem"),
                "hora_postagem": metadados.get("hora_postagem"),
                "duracao_segundos": metadados.get("duracao_segundos"),
                "status": _status_de(metadados),
                "video_16_9": f"/videos/{pasta.name}/video_16x9.mp4",
                "video_9_16": f"/videos/{pasta.name}/video_9x16.mp4",
                "thumbnail": f"/videos/{pasta.name}/thumbnail.png?v={int(thumb_path.stat().st_mtime)}" if thumb_path.exists() else None,
                "modificado_em": pasta.stat().st_mtime,
                "tags": tags,
                "publicado": metadados.get("publicado", False),
                "youtube_video_id": metadados.get("youtube_video_id"),
                "publicacao_erro": metadados.get("publicacao_erro"),
                "tem_cenas": bool(metadados.get("cenas")),
                "thumbnail_texto": metadados.get("thumbnail_texto") or metadados.get("titulo") or pasta.name.replace("-", " "),
                "thumbnail_cor": metadados.get("thumbnail_cor", ""),
                "thumbnail_posicao": metadados.get("thumbnail_posicao", "baixo-centro"),
                "thumbnail_tamanho_px": _tamanho_fonte_de(metadados),
                "thumbnail_pos_x": metadados.get("thumbnail_pos_x"),
                "thumbnail_pos_y": metadados.get("thumbnail_pos_y"),
                "thumbnail_base": _thumbnail_base_url(pasta),
            }
        )

    # vídeos novos ainda sendo gerados (sem pasta/mp4 ainda) — mostra na Fila
    # como "processando" em vez de simplesmente não aparecer até terminar.
    # Regenerar/cena não entra aqui: a pasta e os mp4 antigos já existem, então
    # já aparecem no loop acima com o status de sempre até o novo mp4 sobrescrever.
    slugs_existentes = {v["slug"] for v in videos}
    for job in jobs.listar_rodando():
        slug_job = slug_titulo(job.titulo)
        if slug_job in slugs_existentes:
            continue
        slugs_existentes.add(slug_job)
        canal_info = canal.obter_canal(job.canal_id or canal.CANAL_PADRAO_ID)
        videos.insert(
            0,
            {
                "slug": slug_job,
                "titulo": job.titulo,
                "canal_id": job.canal_id or canal.CANAL_PADRAO_ID,
                "canal_nome": canal_info["nome"] if canal_info else (job.canal_id or canal.CANAL_PADRAO_ID),
                "sem_narracao": False,
                "som_fundo_tipo": "",
                "data_postagem": None,
                "hora_postagem": None,
                "duracao_segundos": None,
                "status": "processando",
                "job_etapa": job.etapa,
                "job_progresso": job.progresso,
                "video_16_9": None,
                "video_9_16": None,
                "thumbnail": None,
                "modificado_em": time.time(),
                "tags": "",
                "publicado": False,
                "youtube_video_id": None,
                "publicacao_erro": None,
                "tem_cenas": False,
                "thumbnail_texto": job.titulo,
                "thumbnail_cor": "",
                "thumbnail_posicao": "baixo-centro",
                "thumbnail_tamanho_px": 80,
                "thumbnail_pos_x": None,
                "thumbnail_pos_y": None,
                "thumbnail_base": None,
            },
        )
    return videos
