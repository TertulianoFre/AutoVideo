"""Pasta de entrada: cada canal tem a sua subpasta (dados/entrada/<canal>). Tudo que você salvar numa delas (imagens e
vídeos gerados no Grok ou em qualquer outro lugar) entra sozinho na Base DAQUELE canal, sem precisar usar o botão de
importar. Arquivos soltos na pasta principal vão para o canal ativo. Depois é só escolher na cena ("Usar da Base")."""

import json
import re
import shutil
import threading
import unicodedata
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


# ---------------- pastas de vídeo: dados/entrada/<canal>/Vídeo 1, Vídeo 2... ----------------
# Cada pasta guarda os arquivos das cenas de UM vídeo (cena 1, cena 2...). Fica onde você colocou; só entra na Base
# (uma vez, sem duplicar) quando você escolhe a pasta no Novo vídeo.

_RE_NUMERO = re.compile(r"(\d+)")
_RE_PASTA_VIDEO = re.compile(r"^v[ií]deo\s+(\d+)$", re.IGNORECASE)


def _ordem_natural(caminho: Path) -> tuple:
    """cena 1, cena 2, ..., cena 10 (e não cena 1, cena 10, cena 2). Sem número no nome: depois, em ordem alfabética."""
    achou = _RE_NUMERO.search(caminho.stem)
    return (0, int(achou.group(1)), caminho.name.lower()) if achou else (1, 0, caminho.name.lower())


def _arquivos_da_pasta(pasta: Path) -> list:
    return sorted(
        (f for f in pasta.iterdir() if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in EXT_IMAGEM | EXT_VIDEO),
        key=_ordem_natural,
    )


def _pasta_de_video_valida(canal_id: str, nome: str) -> Path | None:
    """A subpasta pedida, só se for mesmo uma pasta de vídeo desse canal (nada de sair da pasta de entrada)."""
    if not canal.obter_canal(canal_id) or not nome or "/" in nome or "\\" in nome or nome.startswith(".") or nome == NOME_IMPORTADOS:
        return None
    pasta = pasta_do_canal(canal_id) / nome
    return pasta if pasta.is_dir() else None


def pastas_de_video(canal_id: str) -> list:
    """[{nome, caminho, arquivos: n}] das pastas de vídeo do canal, na ordem natural (Vídeo 2 antes de Vídeo 10)."""
    raiz = pasta_do_canal(canal_id)
    if not raiz.is_dir():
        return []
    pastas = [p for p in raiz.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name != NOME_IMPORTADOS]
    pastas.sort(key=_ordem_natural)
    return [{"nome": p.name, "caminho": str(p), "arquivos": len(_arquivos_da_pasta(p))} for p in pastas]


def criar_pasta_de_video(canal_id: str) -> dict:
    """Cria a próxima pasta: "Vídeo 1", "Vídeo 2"... (o número seguinte ao maior que já existe)."""
    garantir_pasta()
    numeros = [int(m.group(1)) for p in pastas_de_video(canal_id) if (m := _RE_PASTA_VIDEO.match(p["nome"]))]
    nome = f"Vídeo {max(numeros, default=0) + 1}"
    (pasta_do_canal(canal_id) / nome).mkdir(parents=True, exist_ok=True)
    return {"nome": nome, "caminho": str(pasta_do_canal(canal_id) / nome), "arquivos": 0}


def preparar_pasta_de_video(canal_id: str, nome: str) -> list:
    """Coloca na Base do canal os arquivos da pasta que ainda não estão lá e devolve, na ordem das cenas,
    [{arquivo, chave ("imagem:x"|"video:y"), descricao}]. Já importado (mesmo arquivo, sem alteração) é reaproveitado."""
    pasta = _pasta_de_video_valida(canal_id, nome)
    if pasta is None:
        raise ValueError("pasta de vídeo não encontrada")
    caminho_registro = pasta / ".base.json"
    try:
        registro = json.loads(caminho_registro.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        registro = {}
    saida = []
    with _trava:
        for arquivo in _arquivos_da_pasta(pasta):
            info = arquivo.stat()
            assinatura = f"{info.st_size}:{int(info.st_mtime)}"
            eh_imagem = arquivo.suffix.lower() in EXT_IMAGEM
            tipo = "imagens" if eh_imagem else "videos"
            anterior = registro.get(arquivo.name) or {}
            existe = biblioteca.caminho_imagem_valida(anterior.get("nome", "")) if eh_imagem else biblioteca.caminho_video_valido(anterior.get("nome", ""))
            if not (anterior.get("assinatura") == assinatura and anterior.get("tipo") == tipo and existe):
                if info.st_size == 0 or time.time() - info.st_mtime < 4:
                    raise ValueError(f'"{arquivo.name}" ainda está sendo salvo — espere alguns segundos e escolha a pasta de novo')
                conteudo = arquivo.read_bytes()
                sugerido = unicodedata.normalize("NFKD", f"{canal_id}-{pasta.name}-{arquivo.stem}").encode("ascii", "ignore").decode()
                nome_base = biblioteca.salvar_imagem(sugerido, conteudo) if eh_imagem else biblioteca.salvar_video(sugerido, conteudo)
                _marcar_canal(tipo, nome_base, canal_id)
                anterior = {"nome": nome_base, "tipo": tipo, "assinatura": assinatura}
                registro[arquivo.name] = anterior
            saida.append({"arquivo": arquivo.name, "chave": f"{'imagem' if eh_imagem else 'video'}:{anterior['nome']}", "tipo": tipo, "nome": anterior["nome"]})
        caminho_registro.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    return saida
