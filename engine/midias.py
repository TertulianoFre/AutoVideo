"""Descrição das imagens/vídeos da Base, usada pra IA escrever um roteiro que combine com o que vai aparecer.
A IA gratuita de texto NÃO enxerga imagens (testado), então a base é o que você escreveu na descrição do item
na aba Base; sem descrição, usa o nome do arquivo."""

import json
import re
from pathlib import Path

from engine import biblioteca

ARQUIVO_META = biblioteca.RAIZ / "meta.json"


def _meta() -> dict:
    try:
        return json.loads(ARQUIVO_META.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _nome_legivel(nome: str) -> str:
    return re.sub(r"[-_]+", " ", Path(nome).stem).strip()


def descricao_da_midia(tipo: str, nome: str) -> str:
    """tipo: "imagem" | "video". Sempre devolve algo (no pior caso, o nome do arquivo)."""
    item = (_meta().get("videos" if tipo == "video" else "imagens") or {}).get(nome) or {}
    return (item.get("descricao") or "").strip() or _nome_legivel(nome)


def analisar_entradas(entradas: list) -> list:
    """['imagem:a.png', 'video:b.mp4', 'c.png'] -> [('imagem','a.png'), ('video','b.mp4'), ('imagem','c.png')] (só as que existem na Base)."""
    saida = []
    for e in entradas or []:
        tipo, _, nome = str(e).partition(":")
        if not nome:
            tipo, nome = "imagem", tipo
        if tipo == "video" and biblioteca.caminho_video_valido(nome):
            saida.append(("video", nome))
        elif tipo == "imagem" and biblioteca.caminho_imagem_valida(nome):
            saida.append(("imagem", nome))
    return saida


def descricoes_para_roteiro(entradas: list) -> list:
    """Uma descrição por mídia escolhida, na ordem das cenas."""
    return [descricao_da_midia(tipo, nome) for tipo, nome in analisar_entradas(entradas)]
