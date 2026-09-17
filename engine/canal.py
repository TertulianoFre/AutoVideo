"""Contexto do canal — uma descrição livre (nicho, tom, público) guardada uma
vez e usada como base sempre que um roteiro é gerado, pra manter os vídeos
alinhados com a linha do canal."""

import json
from pathlib import Path

CAMINHO_CONFIG = Path(__file__).resolve().parent.parent / "dados" / "canal.json"


def obter_contexto() -> str:
    if not CAMINHO_CONFIG.exists():
        return ""
    dados = json.loads(CAMINHO_CONFIG.read_text(encoding="utf-8"))
    return dados.get("contexto", "")


def salvar_contexto(contexto: str) -> None:
    CAMINHO_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CAMINHO_CONFIG.write_text(
        json.dumps({"contexto": contexto.strip()}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
