"""Backend do app: serve a tela e a API que aciona o motor de geração.

Rodar: .venv\\Scripts\\uvicorn backend.main:app --reload
"""

import json
import random
import sys
import threading
import time
from pathlib import Path

# O texto gerado por IA às vezes traz pontuação Unicode especial (hífen
# não-quebrável, travessão...) que quebra o print() no console do Windows
# (codepage padrão não sabe codificar) — evita que um log derrube o servidor.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import jobs
from engine import agendador, agente, canal, roteiro as roteiro_mod
from engine import thumbnail as thumbnail_mod
from engine import youtube as youtube_mod
from engine.pipeline import RAIZ_SAIDA

RAIZ = Path(__file__).resolve().parent.parent
FRONTEND = RAIZ / "frontend"

RAIZ_SAIDA.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Projeto YT")

# roda junto com o app inteiro: confere de tempos em tempos se algum vídeo
# tem data de postagem vencida e publica sozinho no YouTube (cada um na conta
# do canal dele — engine.agendador resolve isso por vídeo).
agendador.iniciar_agendador()

# status de conexão do YouTube é por canal (dois canais podem estar
# conectando ao mesmo tempo, em tese) — chave é o canal_id.
_estado_conexao_youtube: dict[str, dict] = {}


def _estado_de(canal_id: str) -> dict:
    return _estado_conexao_youtube.setdefault(canal_id, {"status": "ocioso", "erro": None})


app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")
app.mount("/videos", StaticFiles(directory=RAIZ_SAIDA), name="videos")


@app.get("/", response_class=HTMLResponse)
def pagina_inicial() -> str:
    return (FRONTEND / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# canais: cada um tem nome, contexto (nicho/tom/público) e conta do YouTube
# própria. Um fica "ativo" por vez — é o que Novo Vídeo/Agente usam; a Fila
# mostra vídeos de todos os canais.
# ---------------------------------------------------------------------------

@app.get("/api/canais")
def api_listar_canais() -> dict:
    return {"canais": canal.listar_canais(), "ativo": canal.canal_ativo_id()}


@app.post("/api/canais")
def api_criar_canal(nome: str = Form(...), contexto: str = Form("")) -> dict:
    try:
        novo = canal.criar_canal(nome, contexto)
    except ValueError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=400)
    return {"canal": novo}


@app.post("/api/canais/{canal_id}/ativar")
def api_ativar_canal(canal_id: str) -> dict:
    try:
        canal.definir_ativo(canal_id)
    except ValueError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=404)
    return {"ok": True}


@app.post("/api/canais/{canal_id}/editar")
def api_editar_canal(canal_id: str, nome: str = Form(""), contexto: str = Form("")) -> dict:
    try:
        atualizado = canal.atualizar_canal(canal_id, nome=nome or None, contexto=contexto)
    except ValueError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=404)
    return {"canal": atualizado}


# ---------------------------------------------------------------------------
# conexão com o YouTube (publicação automática) — uma conta por canal
# ---------------------------------------------------------------------------

def _conta_do_canal(canal_id: str | None) -> str:
    info = canal.obter_canal(canal_id or canal.canal_ativo_id())
    return info["conta_youtube"] if info else canal.CANAL_PADRAO_ID


@app.get("/api/youtube/status")
def api_youtube_status(canal_id: str | None = None) -> dict:
    conta = _conta_do_canal(canal_id)
    estado = _estado_de(conta)
    return {
        "conectado": youtube_mod.esta_conectado(conta),
        "conectando": estado["status"] == "conectando",
        "erro": estado["erro"],
        "client_secret_presente": youtube_mod.CLIENT_SECRET_PATH.exists(),
    }


@app.post("/api/youtube/conectar")
def api_youtube_conectar(canal_id: str | None = Form(None)) -> dict:
    conta = _conta_do_canal(canal_id)
    estado = _estado_de(conta)
    if estado["status"] == "conectando":
        return {"status": "conectando"}

    estado["status"] = "conectando"
    estado["erro"] = None

    def rodar() -> None:
        try:
            youtube_mod.conectar(conta)
            estado["status"] = "conectado"
        except Exception as erro:
            estado["status"] = "erro"
            estado["erro"] = str(erro)

    # abre o navegador padrão do sistema e espera você autorizar — não pode
    # rodar na thread principal, ia travar o servidor até você terminar.
    threading.Thread(target=rodar, daemon=True).start()
    return {"status": "conectando"}


@app.get("/api/youtube/estatisticas")
def api_youtube_estatisticas(canal_id: str | None = None) -> JSONResponse:
    try:
        return JSONResponse(youtube_mod.obter_estatisticas_canal(_conta_do_canal(canal_id)))
    except Exception as erro:
        # inclui HttpError da API do Google (ex: token sem o escopo readonly
        # ainda, porque foi conectado antes desse escopo existir).
        return JSONResponse({"erro": str(erro)}, status_code=409)


# ---------------------------------------------------------------------------
# agente: sugere ideias de vídeo (opcionalmente inspirado em tendências)
# ---------------------------------------------------------------------------

@app.post("/api/agente/sugestoes")
def api_agente_sugestoes() -> JSONResponse:
    """Sempre sobre o canal ATIVO — é ele que define o contexto e a conta do
    YouTube usados pra puxar tendências."""
    conta = _conta_do_canal(None)
    tendencias = []
    aviso_tendencias = None
    if youtube_mod.esta_conectado(conta):
        try:
            tendencias = youtube_mod.obter_tendencias(conta)
        except Exception as erro:
            aviso_tendencias = f"Não consegui buscar tendências ({erro}) — sugestões vão sair sem esse contexto."
    else:
        aviso_tendencias = "Conecte o YouTube (na aba Canais) pra sugestões levarem em conta o que está em alta."

    try:
        ideias = agente.sugerir_ideias(canal.obter_contexto(), tendencias)
    except RuntimeError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=502)

    return JSONResponse({"ideias": ideias, "aviso": aviso_tendencias})


# ---------------------------------------------------------------------------
# pré-visualização do roteiro (antes de gerar o vídeo inteiro)
# ---------------------------------------------------------------------------

@app.post("/api/roteiro/preview")
def api_preview_roteiro(
    titulo: str = Form(...),
    duracao_alvo: float | None = Form(None),
    descricao_video: str = Form(""),
) -> JSONResponse:
    try:
        roteiro = roteiro_mod.gerar_roteiro(
            titulo.strip(),
            duracao_alvo or 1.0,
            contexto_canal=canal.obter_contexto(),
            descricao_video=descricao_video.strip(),
        )
        return JSONResponse({"roteiro": roteiro})
    except RuntimeError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=502)


# ---------------------------------------------------------------------------
# geração de vídeo
# ---------------------------------------------------------------------------

@app.post("/api/videos")
def api_criar_video(
    titulo: str = Form(...),
    data_postagem: str = Form(...),
    roteiro: str = Form(""),
    descricao_video: str = Form(""),
    idioma: str = Form("pt-BR"),
    voz: str = Form("mulher"),
    imagem: str = Form("procedural"),
    duracao_alvo: float | None = Form(None),
    sem_narracao: bool = Form(False),
    som_fundo_tipo: str = Form(""),
    som_fundo_descricao: str = Form(""),
) -> dict:
    titulo = titulo.strip()
    params = dict(
        titulo=titulo,
        roteiro=None if sem_narracao else (roteiro.strip() or None),
        idioma=idioma,
        voz=voz,
        estilo_imagem=imagem,
        duracao_alvo_minutos=duracao_alvo,
        descricao_video=descricao_video.strip(),
        data_postagem=data_postagem,
        sem_narracao=sem_narracao,
        som_fundo_tipo=som_fundo_tipo,
        som_fundo_descricao=som_fundo_descricao.strip(),
        canal_id=canal.canal_ativo_id(),  # vídeo pertence ao canal ativo no momento em que foi criado
    )

    job = jobs.criar_job(titulo, params)
    return {"job_id": job.id}


@app.post("/api/videos/{slug}/regenerar")
def api_regenerar_video(slug: str, manter_roteiro: bool = Form(True)) -> dict:
    """Gera tudo de novo — narração, imagens, montagem. Por padrão mantém o
    roteiro já existente (o problema geralmente é imagem, não texto); passe
    manter_roteiro=false pra escrever um roteiro novo também."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    titulo = metadados.get("titulo", slug)
    sem_narracao = metadados.get("sem_narracao", False)

    roteiro_existente = None
    caminho_roteiro = pasta / "roteiro.txt"
    if manter_roteiro and not sem_narracao and caminho_roteiro.exists():
        roteiro_existente = caminho_roteiro.read_text(encoding="utf-8")

    params = dict(
        titulo=titulo,
        roteiro=roteiro_existente,
        idioma=metadados.get("idioma", "pt-BR"),
        voz=metadados.get("voz", "mulher"),
        estilo_imagem=metadados.get("estilo_imagem", "procedural"),
        duracao_alvo_minutos=metadados.get("duracao_alvo_minutos") or (15.0 if sem_narracao else 1.0),
        descricao_video=metadados.get("descricao_video", ""),
        data_postagem=metadados.get("data_postagem"),
        sem_narracao=sem_narracao,
        som_fundo_tipo=metadados.get("som_fundo_tipo", ""),
        som_fundo_descricao=metadados.get("som_fundo_descricao", ""),
        canal_id=metadados.get("canal_id"),  # mantém o canal original do vídeo, não o ativo agora
    )

    job = jobs.criar_job(titulo, params)
    return {"job_id": job.id}


@app.post("/api/videos/{slug}/thumbnail/regenerar")
def api_regenerar_thumbnail(slug: str) -> dict:
    """Refaz só a thumbnail (rápido, não mexe no vídeo) — sorteia uma imagem
    de cena diferente da atual como base, pra você poder ficar pedindo outra
    até gostar."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    candidatas = sorted(pasta.glob("cena*_16x9.png"))
    if not candidatas:
        return JSONResponse({"erro": "não achei nenhuma imagem de cena pra usar de base"}, status_code=404)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    texto = metadados.get("thumbnail_texto") or metadados.get("titulo", slug)
    cor = thumbnail_mod.cor_de_hex(metadados.get("thumbnail_cor", ""))
    posicao = metadados.get("thumbnail_posicao", "baixo-centro")
    tamanho_fonte = thumbnail_mod.TAMANHOS.get(metadados.get("thumbnail_tamanho", "medio"), 80)

    atual = pasta / "thumbnail_fonte.txt"
    fonte_anterior = atual.read_text(encoding="utf-8").strip() if atual.exists() else None
    opcoes = [c for c in candidatas if c.name != fonte_anterior] or candidatas
    escolhida = random.choice(opcoes)

    thumbnail_mod.gerar_thumbnail(escolhida, texto, pasta / "thumbnail.png", cor, posicao, tamanho_fonte)
    atual.write_text(escolhida.name, encoding="utf-8")

    return {"thumbnail": f"/videos/{slug}/thumbnail.png?v={int(time.time())}"}


@app.post("/api/videos/{slug}/thumbnail/editar")
def api_editar_thumbnail(
    slug: str,
    texto: str = Form(...),
    cor: str = Form(""),
    posicao: str = Form("baixo-centro"),
    tamanho: str = Form("medio"),
) -> dict:
    """Troca o texto, a cor, a posição e o tamanho da thumbnail, mantendo a
    mesma imagem de base atual. Fica salvo pro vídeo (sobrevive a "nova
    thumbnail" e a regenerar a cena 0) até você editar de novo."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    texto = texto.strip()
    if not texto:
        return JSONResponse({"erro": "o texto da thumbnail não pode ficar vazio"}, status_code=400)

    fonte_txt = pasta / "thumbnail_fonte.txt"
    fonte_nome = fonte_txt.read_text(encoding="utf-8").strip() if fonte_txt.exists() else "cena00_16x9.png"
    base = pasta / fonte_nome
    if not base.exists():
        candidatas = sorted(pasta.glob("cena*_16x9.png"))
        if not candidatas:
            return JSONResponse({"erro": "não achei nenhuma imagem de cena pra usar de base"}, status_code=404)
        base = candidatas[0]

    cor_rgb = thumbnail_mod.cor_de_hex(cor)
    posicao = posicao if posicao in thumbnail_mod.POSICOES else "baixo-centro"
    tamanho = tamanho if tamanho in thumbnail_mod.TAMANHOS else "medio"
    thumbnail_mod.gerar_thumbnail(base, texto, pasta / "thumbnail.png", cor_rgb, posicao, thumbnail_mod.TAMANHOS[tamanho])

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    metadados["thumbnail_texto"] = texto
    metadados["thumbnail_cor"] = cor.strip().lstrip("#") if cor_rgb else ""
    metadados["thumbnail_posicao"] = posicao
    metadados["thumbnail_tamanho"] = tamanho
    caminho_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"thumbnail": f"/videos/{slug}/thumbnail.png?v={int(time.time())}"}


@app.get("/api/videos/{slug}/cenas")
def api_listar_cenas(slug: str) -> dict:
    """Lista as cenas do vídeo (texto + imagem de cada uma) pra edição pontual."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    cenas = metadados.get("cenas")
    if not cenas:
        return JSONResponse(
            {"erro": 'Esse vídeo foi gerado antes desse recurso existir — clique em "Regenerar" uma vez pra habilitar.'},
            status_code=409,
        )

    resultado = []
    for i, cena in enumerate(cenas):
        caminho_imagem = pasta / f"cena{i:02d}_16x9.png"
        resultado.append(
            {
                "indice": i,
                "texto": cena.get("texto", ""),
                "duracao_segundos": cena.get("duracao_segundos", 0),
                "imagem": f"/videos/{slug}/cena{i:02d}_16x9.png?v={int(caminho_imagem.stat().st_mtime)}" if caminho_imagem.exists() else None,
            }
        )
    return {"cenas": resultado}


@app.post("/api/videos/{slug}/cenas/{indice}/regenerar")
def api_regenerar_cena(slug: str, indice: int) -> dict:
    """Refaz só a imagem de uma cena e remonta o vídeo — não mexe em roteiro,
    narração nem nas outras cenas."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    titulo = metadados.get("titulo", slug)

    job = jobs.criar_job_cena(titulo, slug, indice)
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
        thumb_path = pasta / "thumbnail.png"

        canal_id_video = metadados.get("canal_id") or canal.CANAL_PADRAO_ID
        canal_info = canal.obter_canal(canal_id_video)

        videos.append(
            {
                "slug": pasta.name,
                "titulo": metadados.get("titulo") or pasta.name.replace("-", " "),
                "canal_id": canal_id_video,
                "canal_nome": canal_info["nome"] if canal_info else canal_id_video,
                "sem_narracao": metadados.get("sem_narracao", False),
                "som_fundo_tipo": metadados.get("som_fundo_tipo", ""),
                "data_postagem": metadados.get("data_postagem"),
                "video_16_9": f"/videos/{pasta.name}/video_16x9.mp4",
                "video_9_16": f"/videos/{pasta.name}/video_9x16.mp4",
                "thumbnail": f"/videos/{pasta.name}/thumbnail.png?v={int(thumb_path.stat().st_mtime)}" if thumb_path.exists() else None,
                "modificado_em": pasta.stat().st_mtime,
                "tags": tags,
                "publicado": metadados.get("publicado", False),
                "youtube_video_id": metadados.get("youtube_video_id"),
                "publicacao_erro": metadados.get("publicacao_erro"),
                "tem_cenas": bool(metadados.get("cenas")),
                "thumbnail_texto": metadados.get("thumbnail_texto") or metadados.get("titulo") or pasta.name.replace("-", " "),
                "thumbnail_cor": metadados.get("thumbnail_cor", ""),
                "thumbnail_posicao": metadados.get("thumbnail_posicao", "baixo-centro"),
                "thumbnail_tamanho": metadados.get("thumbnail_tamanho", "medio"),
            }
        )
    return videos
