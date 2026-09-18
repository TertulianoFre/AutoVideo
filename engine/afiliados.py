"""Afiliados: guarda links de produtos (TikTok Shop, Shopee, etc.) que você
quer divulgar nos vídeos pra ganhar comissão nas vendas. Por enquanto é só
uma lista que você mantém manualmente — nenhum vídeo insere esses links
sozinho ainda; é o espaço reservado pra essa ideia evoluir."""

import json
import uuid
from pathlib import Path

CAMINHO = Path(__file__).resolve().parent.parent / "dados" / "afiliados.json"

PLATAFORMAS = ["tiktok_shop", "shopee", "outro"]


def _carregar() -> list[dict]:
    if not CAMINHO.exists():
        return []
    try:
        return json.loads(CAMINHO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _salvar(itens: list[dict]) -> None:
    CAMINHO.parent.mkdir(parents=True, exist_ok=True)
    CAMINHO.write_text(json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8")


def listar() -> list[dict]:
    return _carregar()


def adicionar(nome: str, plataforma: str, link: str, nota: str = "") -> dict:
    item = {
        "id": str(uuid.uuid4()),
        "nome": nome.strip(),
        "plataforma": plataforma if plataforma in PLATAFORMAS else "outro",
        "link": link.strip(),
        "nota": nota.strip(),
    }
    itens = _carregar()
    itens.append(item)
    _salvar(itens)
    return item


def remover(item_id: str) -> bool:
    itens = _carregar()
    restantes = [i for i in itens if i["id"] != item_id]
    if len(restantes) == len(itens):
        return False
    _salvar(restantes)
    return True
