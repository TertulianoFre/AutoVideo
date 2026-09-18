"""Canais do app: cada canal tem um nome, um contexto (nicho/tom/público) e
uma conta do YouTube própria (mesmo id do canal). Múltiplos canais = múltiplos
"negócios" rodando no mesmo app, cada um com seu próprio conteúdo e destino de
publicação — só um fica "ativo" por vez (usado por Novo Vídeo/Agente); a Fila
mostra vídeos de todos.

Sempre existe pelo menos o canal "principal". Se o app já tinha o arquivo
antigo de contexto único (dados/canal.json, de antes desse recurso existir),
o contexto dele é migrado pro canal "principal" na primeira leitura."""

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO = RAIZ / "dados" / "canais.json"
CAMINHO_ANTIGO = RAIZ / "dados" / "canal.json"

CANAL_PADRAO_ID = "principal"


def _slug(texto: str) -> str:
    texto = texto.strip().lower()
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    return texto.strip("-")[:40]


def _contexto_migrado() -> str:
    if not CAMINHO_ANTIGO.exists():
        return ""
    try:
        return json.loads(CAMINHO_ANTIGO.read_text(encoding="utf-8")).get("contexto", "")
    except (json.JSONDecodeError, OSError):
        return ""


def _dados_padrao() -> dict:
    return {
        "canais": [{"id": CANAL_PADRAO_ID, "nome": "Canal principal", "contexto": _contexto_migrado(), "conta_youtube": CANAL_PADRAO_ID}],
        "ativo": CANAL_PADRAO_ID,
    }


def _carregar() -> dict:
    if not CAMINHO.exists():
        dados = _dados_padrao()
        _salvar(dados)
        return dados
    try:
        dados = json.loads(CAMINHO.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _dados_padrao()
    if not dados.get("canais"):
        return _dados_padrao()
    return dados


def _salvar(dados: dict) -> None:
    CAMINHO.parent.mkdir(parents=True, exist_ok=True)
    CAMINHO.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def listar_canais() -> list:
    return _carregar()["canais"]


def obter_canal(canal_id: str) -> dict | None:
    for c in listar_canais():
        if c["id"] == canal_id:
            return c
    return None


def canal_ativo_id() -> str:
    dados = _carregar()
    ids = [c["id"] for c in dados["canais"]]
    if dados.get("ativo") in ids:
        return dados["ativo"]
    return dados["canais"][0]["id"]


def definir_ativo(canal_id: str) -> None:
    dados = _carregar()
    if not any(c["id"] == canal_id for c in dados["canais"]):
        raise ValueError(f"Canal '{canal_id}' não existe.")
    dados["ativo"] = canal_id
    _salvar(dados)


def criar_canal(nome: str, contexto: str = "") -> dict:
    nome = nome.strip()
    if not nome:
        raise ValueError("Dê um nome pro canal.")

    dados = _carregar()
    ids_existentes = {c["id"] for c in dados["canais"]}
    base_id = _slug(nome) or "canal"
    canal_id = base_id
    n = 2
    while canal_id in ids_existentes:
        canal_id = f"{base_id}-{n}"
        n += 1

    novo = {"id": canal_id, "nome": nome, "contexto": contexto.strip(), "conta_youtube": canal_id}
    dados["canais"].append(novo)
    _salvar(dados)
    return novo


def atualizar_canal(canal_id: str, nome: str | None = None, contexto: str | None = None, conta_youtube: str | None = None) -> dict:
    """conta_youtube: normalmente é o mesmo id do canal (1 conta por canal) —
    só precisa mexer aqui pra apontar esse canal pra uma conta do YouTube já
    conectada com outro nome (ex: reaproveitar uma conta entre dois canais)
    sem precisar recriar o canal inteiro. String vazia é ignorada (não dá pra
    deixar um canal sem nenhuma conta associada)."""
    dados = _carregar()
    for c in dados["canais"]:
        if c["id"] == canal_id:
            if nome is not None and nome.strip():
                c["nome"] = nome.strip()
            if contexto is not None:
                c["contexto"] = contexto.strip()
            if conta_youtube is not None and conta_youtube.strip():
                c["conta_youtube"] = conta_youtube.strip()
            _salvar(dados)
            return c
    raise ValueError(f"Canal '{canal_id}' não existe.")


def obter_contexto(canal_id: str | None = None) -> str:
    """Contexto do canal dado, ou do canal ativo se não especificar."""
    canal = obter_canal(canal_id or canal_ativo_id())
    return canal["contexto"] if canal else ""
