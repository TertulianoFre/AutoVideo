"""Backend do app: serve a tela e a API que aciona o motor de geração.

Rodar: .venv\\Scripts\\uvicorn backend.main:app --reload
"""

import json
import random
import sys
import threading
import time
from pathlib import Path

# O texto gerado por IA às vezes traz pontuação Unicode especial (hífen
# não-quebrável, travessão...) que quebra o print() no console do Windows
# (codepage padrão não sabe codificar) — evita que um log derrube o servidor.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import jobs
from engine import agendador, canal, roteiro as roteiro_mod
from engine import thumbnail as thumbnail_mod
from engine import youtube as youtube_mod
from engine.pipeline import RAIZ_SAIDA

RAIZ = Path(__file__).resolve().parent.parent
FRONTEND = RAIZ / "frontend"

RAIZ_SAIDA.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Projeto YT")

# roda junto com o app inteiro: confere de tempos em tempos se algum vídeo
# tem data de postagem vencida e publica sozinho no YouTube.
agendador.iniciar_agendador()

CONTA_YOUTUBE_PADRAO = "principal"
_estado_conexao_youtube = {"status": "ocioso", "erro": None}  # ocioso | conectando | conectado | erro

app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")
app.mount("/videos", StaticFiles(directory=RAIZ_SAIDA), name="videos")


@app.get("/", response_class=HTMLResponse)
def pagina_inicial() -> str:
    return (FRONTEND / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# contexto do canal
# ---------------------------------------------------------------------------

@app.get("/api/canal")
def api_obter_canal() -> dict:
    return {"contexto": canal.obter_contexto()}


@app.post("/api/canal")
def api_salvar_canal(contexto: str = Form("")) -> dict:
    canal.salvar_contexto(contexto)
    return {"ok": True}


# ---------------------------------------------------------------------------
# conexão com o YouTube (publicação automática)
# ---------------------------------------------------------------------------

@app.get("/api/youtube/status")
def api_youtube_status() -> dict:
    return {
        "conectado": youtube_mod.esta_conectado(CONTA_YOUTUBE_PADRAO),
        "conectando": _estado_conexao_youtube["status"] == "conectando",
        "erro": _estado_conexao_youtube["erro"],
        "client_secret_presente": youtube_mod.CLIENT_SECRET_PATH.exists(),
    }


@app.post("/api/youtube/conectar")
def api_youtube_conectar() -> dict:
    if _estado_conexao_youtube["status"] == "conectando":
        return {"status": "conectando"}

    _estado_conexao_youtube["status"] = "conectando"
    _estado_conexao_youtube["erro"] = None

    def rodar() -> None:
        try:
            youtube_mod.conectar(CONTA_YOUTUBE_PADRAO)
            _estado_conexao_youtube["status"] = "conectado"
        except Exception as erro:
            _estado_conexao_youtube["status"] = "erro"
            _estado_conexao_youtube["erro"] = str(erro)

    # abre o navegador padrão do sistema e espera você autorizar — não pode
    # rodar na thread principal, ia travar o servidor até você terminar.
    threading.Thread(target=rodar, daemon=True).start()
    return {"status": "conectando"}


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
    roteiro: str = Form(""),
    descricao_video: str = Form(""),
    idioma: str = Form("pt-BR"),
    voz: str = Form("mulher"),
    imagem: str = Form("procedural"),
    duracao_alvo: float | None = Form(None),
    sem_narracao: bool = Form(False),
    som_fundo_tipo: str = Form(""),
    som_fundo_descricao: str = Form(""),
) -> dict:
    titulo = titulo.strip()
    params = dict(
        titulo=titulo,
        roteiro=None if sem_narracao else (roteiro.strip() or None),
        idioma=idioma,
        voz=voz,
        estilo_imagem=imagem,
        duracao_alvo_minutos=duracao_alvo,
        descricao_video=descricao_video.strip(),
        data_postagem=data_postagem,
        sem_narracao=sem_narracao,
        som_fundo_tipo=som_fundo_tipo,
        som_fundo_descricao=som_fundo_descricao.strip(),
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
        sem_narracao=sem_narracao,
        som_fundo_tipo=metadados.get("som_fundo_tipo", ""),
        som_fundo_descricao=metadados.get("som_fundo_descricao", ""),
    )

    job = jobs.criar_job(titulo, params)
    return {"job_id": job.id}


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
    titulo = metadados.get("titulo", slug)

    atual = pasta / "thumbnail_fonte.txt"
    fonte_anterior = atual.read_text(encoding="utf-8").strip() if atual.exists() else None
    opcoes = [c for c in candidatas if c.name != fonte_anterior] or candidatas
    escolhida = random.choice(opcoes)

    thumbnail_mod.gerar_thumbnail(escolhida, titulo, pasta / "thumbnail.png")
    atual.write_text(escolhida.name, encoding="utf-8")

    return {"thumbnail": f"/videos/{slug}/thumbnail.png?v={int(time.time())}"}


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

        videos.append(
            {
                "slug": pasta.name,
                "titulo": metadados.get("titulo") or pasta.name.replace("-", " "),
                "sem_narracao": metadados.get("sem_narracao", False),
                "som_fundo_tipo": metadados.get("som_fundo_tipo", ""),
                "data_postagem": metadados.get("data_postagem"),
                "video_16_9": f"/videos/{pasta.name}/video_16x9.mp4",
                "video_9_16": f"/videos/{pasta.name}/video_9x16.mp4",
                "thumbnail": f"/videos/{pasta.name}/thumbnail.png?v={int(thumb_path.stat().st_mtime)}" if thumb_path.exists() else None,
                "modificado_em": pasta.stat().st_mtime,
                "tags": tags,
                "publicado": metadados.get("publicado", False),
                "youtube_video_id": metadados.get("youtube_video_id"),
                "publicacao_erro": metadados.get("publicacao_erro"),
            }
        )
    return videos
