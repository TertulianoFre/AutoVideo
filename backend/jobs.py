"""Gerencia os jobs de geração de vídeo em background, com progresso real."""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from engine.pipeline import gerar_video

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


def _rodar(job: Job, params: dict) -> None:
    def progresso_cb(etapa: str, percentual: float) -> None:
        job.etapa = etapa
        job.progresso = round(percentual, 1)

    try:
        resultado = gerar_video(progresso=progresso_cb, **params)
        job.resultado = {
            "slug": resultado.pasta.name,
            "video_16_9": f"/videos/{resultado.pasta.name}/{resultado.video_16_9.name}",
            "video_9_16": f"/videos/{resultado.pasta.name}/{resultado.video_9_16.name}",
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
    job = Job(id=str(uuid.uuid4()), titulo=titulo)
    with _lock:
        _jobs[job.id] = job

    threading.Thread(target=_rodar, args=(job, params), daemon=True).start()
    return job


def obter_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)
