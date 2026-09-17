"""Backend do app: serve a tela e a API que aciona o motor de geração.

Rodar: .venv\\Scripts\\uvicorn backend.main:app --reload
"""

import json
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import jobs
from engine import canal
from engine.pipeline import RAIZ_SAIDA

RAIZ = Path(__file__).resolve().parent.parent
FRONTEND = RAIZ / "frontend"

RAIZ_SAIDA.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Projeto YT")

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
# geração de vídeo
# ---------------------------------------------------------------------------

@app.post("/api/videos")
def api_criar_video(
    titulo: str = Form(...),
    data_postagem: str = Form(...),
    modo: str = Form("narrado"),
    roteiro: str = Form(""),
    descricao_video: str = Form(""),
    idioma: str = Form("pt-BR"),
    voz: str = Form("mulher"),
    imagem: str = Form("procedural"),
    duracao_alvo: float | None = Form(None),
    tipo_som: str = Form("chuva"),
) -> dict:
    titulo = titulo.strip()
    if modo == "ambiente":
        params = dict(
            titulo=titulo,
            duracao_alvo_minutos=duracao_alvo or 15.0,
            tipo_som=tipo_som,
            estilo_imagem=imagem,
            descricao_video=descricao_video.strip(),
            data_postagem=data_postagem,
        )
    else:
        params = dict(
            titulo=titulo,
            roteiro=roteiro.strip() or None,
            idioma=idioma,
            voz=voz,
            estilo_imagem=imagem,
            duracao_alvo_minutos=duracao_alvo,
            descricao_video=descricao_video.strip(),
            data_postagem=data_postagem,
        )

    job = jobs.criar_job(titulo, modo, params)
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

        videos.append(
            {
                "slug": pasta.name,
                "titulo": metadados.get("titulo") or pasta.name.replace("-", " "),
                "modo": metadados.get("modo", "narrado"),
                "data_postagem": metadados.get("data_postagem"),
                "video_16_9": f"/videos/{pasta.name}/video_16x9.mp4",
                "video_9_16": f"/videos/{pasta.name}/video_9x16.mp4",
                "modificado_em": pasta.stat().st_mtime,
                "tags": tags,
            }
        )
    return videos
