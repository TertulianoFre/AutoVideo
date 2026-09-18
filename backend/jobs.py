"""Gerencia os jobs de geração de vídeo em background, com progresso real."""

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from engine.pipeline import gerar_video, regenerar_cena

_jobs: dict[str, "Job"] = {}
_lock = threading.Lock()


@dataclass
class Job:
    id: str
    titulo: str
    status: str = "rodando"  # rodando | pronto | erro
    etapa: str = "Iniciando"
    progresso: float = 0.0
    criado_em: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resultado: dict | None = None
    erro: str | None = None
    canal_id: str | None = None  # só pra job de vídeo novo — usado pra mostrar "processando" na Fila


def _rodar(job: Job, params: dict) -> None:
    def progresso_cb(etapa: str, percentual: float) -> None:
        job.etapa = etapa
        job.progresso = round(percentual, 1)

    try:
        resultado = gerar_video(progresso=progresso_cb, **params)
        job.resultado = {
            "slug": resultado.pasta.name,
            "video_16_9": f"/videos/{resultado.pasta.name}/{resultado.video_16_9.name}" if resultado.video_16_9 else None,
            "video_9_16": f"/videos/{resultado.pasta.name}/{resultado.video_9_16.name}" if resultado.video_9_16 else None,
            "thumbnail": f"/videos/{resultado.pasta.name}/thumbnail.png" if resultado.thumbnail else None,
            "duracao_segundos": resultado.duracao_segundos,
            "roteiro": resultado.roteiro,
            "tags": resultado.tags,
        }
        job.status = "pronto"
        job.progresso = 100
        job.etapa = "Pronto"
    except Exception as erro:  # qualquer falha do motor vira um status legível pro front
        job.status = "erro"
        job.erro = str(erro)


def criar_job(titulo: str, params: dict) -> Job:
    job = Job(id=str(uuid.uuid4()), titulo=titulo, canal_id=params.get("canal_id"))
    with _lock:
        _jobs[job.id] = job

    threading.Thread(target=_rodar, args=(job, params), daemon=True).start()
    return job


def listar_rodando() -> list[Job]:
    """Jobs de vídeo novo ainda em andamento — usado pra mostrar "processando"
    na Fila antes do vídeo existir de verdade em disco."""
    with _lock:
        return [j for j in _jobs.values() if j.status == "rodando"]


def _rodar_cena(job: Job, slug: str, indice: int, imagem_propria=None) -> None:
    def progresso_cb(etapa: str, percentual: float) -> None:
        job.etapa = etapa
        job.progresso = round(percentual, 1)

    try:
        resultado = regenerar_cena(slug, indice, progresso=progresso_cb, imagem_propria=imagem_propria)
        marca = int(time.time())
        job.resultado = {
            "slug": slug,
            "video_16_9": f"/videos/{slug}/{resultado['video_16_9']}?v={marca}" if resultado["video_16_9"] else None,
            "video_9_16": f"/videos/{slug}/{resultado['video_9_16']}?v={marca}" if resultado["video_9_16"] else None,
            "cena_imagem": f"/videos/{slug}/cena{indice:02d}_16x9.png?v={marca}",
            "cena_imagem_9x16": f"/videos/{slug}/cena{indice:02d}_9x16.png?v={marca}",
            "thumbnail": f"/videos/{slug}/thumbnail.png?v={marca}" if resultado["thumbnail_atualizada"] else None,
        }
        job.status = "pronto"
        job.progresso = 100
        job.etapa = "Pronto"
    except Exception as erro:
        job.status = "erro"
        job.erro = str(erro)


def criar_job_cena(titulo: str, slug: str, indice: int, imagem_propria=None) -> Job:
    job = Job(id=str(uuid.uuid4()), titulo=titulo)
    with _lock:
        _jobs[job.id] = job

    threading.Thread(target=_rodar_cena, args=(job, slug, indice, imagem_propria), daemon=True).start()
    return job


def obter_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)
