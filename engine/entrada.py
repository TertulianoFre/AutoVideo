"""Pasta de entrada: tudo que você salvar aqui (imagens e vídeos gerados no Grok ou em qualquer outro lugar) entra
sozinho na Base do canal ativo, sem precisar usar o botão de importar. Depois é só escolher na cena ("Usar da Base")."""

import json
import shutil
import threading
import time
from pathlib import Path

from engine import biblioteca, canal

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "dados" / "entrada"
IMPORTADOS = PASTA / "importados"
EXT_IMAGEM = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
EXT_VIDEO = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
_trava = threading.Lock()


def garantir_pasta() -> Path:
    IMPORTADOS.mkdir(parents=True, exist_ok=True)
    return PASTA


def pendentes() -> list:
    """Arquivos prontos para importar: só os que já terminaram de ser baixados (não mudam há alguns segundos)."""
    garantir_pasta()
    agora = time.time()
    saida = []
    for f in sorted(PASTA.iterdir()):
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in EXT_IMAGEM | EXT_VIDEO:
            info = f.stat()
            if info.st_size > 0 and agora - info.st_mtime > 4:
                saida.append(f)
    return saida


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
    """Importa tudo que está pendente para a Base do canal (o ativo, se não for dito). Devolve o que entrou e os erros."""
    canal_id = canal_id or canal.canal_ativo_id()
    importados, erros = [], []
    with _trava:
        for arquivo in pendentes():
            try:
                conteudo = arquivo.read_bytes()
                if arquivo.suffix.lower() in EXT_IMAGEM:
                    nome, tipo = biblioteca.salvar_imagem(arquivo.stem, conteudo), "imagens"
                else:
                    nome, tipo = biblioteca.salvar_video(arquivo.stem, conteudo), "videos"
                _marcar_canal(tipo, nome, canal_id)
                destino = IMPORTADOS / arquivo.name
                n = 1
                while destino.exists():
                    destino = IMPORTADOS / f"{arquivo.stem}-{n}{arquivo.suffix}"
                    n += 1
                shutil.move(str(arquivo), str(destino))
                importados.append({"arquivo": arquivo.name, "nome": nome, "tipo": tipo})
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
