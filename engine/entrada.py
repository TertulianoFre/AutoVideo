"""Pasta de entrada: cada canal tem a sua subpasta (dados/entrada/<canal>). Tudo que você salvar numa delas (imagens e
vídeos gerados no Grok ou em qualquer outro lugar) entra sozinho na Base DAQUELE canal, sem precisar usar o botão de
importar. Arquivos soltos na pasta principal vão para o canal ativo. Depois é só escolher na cena ("Usar da Base")."""

import json
import shutil
import threading
import time
from pathlib import Path

from engine import biblioteca, canal

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "dados" / "entrada"
NOME_IMPORTADOS = "importados"
EXT_IMAGEM = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
EXT_VIDEO = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
_trava = threading.Lock()


def pasta_do_canal(canal_id: str) -> Path:
    return PASTA / canal_id


def garantir_pasta() -> Path:
    """Cria a pasta principal e uma subpasta para cada canal (com a de "importados" dentro)."""
    PASTA.mkdir(parents=True, exist_ok=True)
    for c in canal.listar_canais():
        (pasta_do_canal(c["id"]) / NOME_IMPORTADOS).mkdir(parents=True, exist_ok=True)
    (PASTA / NOME_IMPORTADOS).mkdir(exist_ok=True)
    return PASTA


def _prontos(pasta: Path) -> list:
    """Arquivos prontos para importar: só os que já terminaram de ser baixados (não mudam há alguns segundos)."""
    agora = time.time()
    saida = []
    if not pasta.is_dir():
        return saida
    for f in sorted(pasta.iterdir()):
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in EXT_IMAGEM | EXT_VIDEO:
            info = f.stat()
            if info.st_size > 0 and agora - info.st_mtime > 4:
                saida.append(f)
    return saida


def pendentes_por_canal() -> dict:
    """{canal_id: [arquivos]} — o que está esperando em cada subpasta (soltos na principal contam para o canal ativo)."""
    garantir_pasta()
    ativo = canal.canal_ativo_id()
    saida = {c["id"]: _prontos(pasta_do_canal(c["id"])) for c in canal.listar_canais()}
    saida.setdefault(ativo, [])
    saida[ativo] = _prontos(PASTA) + saida[ativo]
    return saida


def pendentes() -> list:
    return [f for lista in pendentes_por_canal().values() for f in lista]


def _marcar_canal(tipo: str, nome: str, canal_id: str) -> None:
    caminho = biblioteca.RAIZ / "meta.json"
    try:
        meta = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    item = meta.setdefault(tipo, {}).setdefault(nome, {})
    item.setdefault("descricao", "")
    item["canal_id"] = canal_id
    caminho.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def importar(canal_id: str | None = None) -> dict:
    """Importa o que está pendente, cada arquivo para a Base do canal da sua subpasta. Com `canal_id`, só esse canal.
    Devolve o que entrou e os erros."""
    importados, erros = [], []
    with _trava:
        lista = [(cid, f) for cid, fs in pendentes_por_canal().items() if not canal_id or cid == canal_id for f in fs]
        for canal_do_arquivo, arquivo in lista:
            IMPORTADOS = (arquivo.parent if arquivo.parent != PASTA else PASTA) / NOME_IMPORTADOS
            IMPORTADOS.mkdir(exist_ok=True)
            try:
                conteudo = arquivo.read_bytes()
                if arquivo.suffix.lower() in EXT_IMAGEM:
                    nome, tipo = biblioteca.salvar_imagem(arquivo.stem, conteudo), "imagens"
                else:
                    nome, tipo = biblioteca.salvar_video(arquivo.stem, conteudo), "videos"
                _marcar_canal(tipo, nome, canal_do_arquivo)
                destino = IMPORTADOS / arquivo.name
                n = 1
                while destino.exists():
                    destino = IMPORTADOS / f"{arquivo.stem}-{n}{arquivo.suffix}"
                    n += 1
                shutil.move(str(arquivo), str(destino))
                importados.append({"arquivo": arquivo.name, "nome": nome, "tipo": tipo, "canal_id": canal_do_arquivo})
            except Exception as erro:
                erros.append({"arquivo": arquivo.name, "erro": str(erro)[:160]})
                shutil.move(str(arquivo), str(IMPORTADOS / f"ERRO-{arquivo.name}")) if arquivo.exists() else None
    return {"importados": importados, "erros": erros}


def iniciar() -> None:
    def laco() -> None:
        while True:
            try:
                importar()
            except Exception as erro:
                print(f"[entrada] erro: {erro}")
            time.sleep(15)

    garantir_pasta()
    threading.Thread(target=laco, daemon=True).start()
