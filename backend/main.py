"""Backend do app: serve a tela e a API que aciona o motor de geração.

Rodar: .venv\\Scripts\\uvicorn backend.main:app --reload
"""

import asyncio
import io
import json
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# O texto gerado por IA às vezes traz pontuação Unicode especial (hífen
# não-quebrável, travessão...) que quebra o print() no console do Windows
# (codepage padrão não sabe codificar) — evita que um log derrube o servidor.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from backend import jobs
from engine import afiliados, agendador, agente, biblioteca, canal, roteiro as roteiro_mod
from engine import canal as canais_mod  # o parâmetro "canal" de alguns endpoints esconde o módulo
from engine import thumbnail as thumbnail_mod
from engine import tts as tts_mod
from engine import estimativa as estimativa_mod
from engine import midias as midias_mod
from engine import pipeline as pipeline_mod
from engine import render as render_mod
from engine import subtitles as subtitles_mod
from engine import youtube as youtube_mod
from engine.pipeline import RAIZ_SAIDA, slug_titulo

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


biblioteca.PASTA_AUDIOS.mkdir(parents=True, exist_ok=True)
biblioteca.PASTA_IMAGENS.mkdir(parents=True, exist_ok=True)

@app.middleware("http")
async def sem_cache_no_front(request, call_next):
    """Front (JS/CSS/HTML) sempre revalida: sem isso o navegador serve arquivo velho depois de uma atualização."""
    resposta = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        resposta.headers["Cache-Control"] = "no-cache"
    return resposta


app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")
app.mount("/videos", StaticFiles(directory=RAIZ_SAIDA), name="videos")
app.mount("/biblioteca", StaticFiles(directory=biblioteca.RAIZ), name="biblioteca")


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
def api_editar_canal(canal_id: str, nome: str = Form(""), contexto: str = Form(""), conta_youtube: str = Form("")) -> dict:
    try:
        atualizado = canal.atualizar_canal(canal_id, nome=nome or None, contexto=contexto, conta_youtube=conta_youtube or None)
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


@app.get("/api/youtube/serie")
def api_youtube_serie(dias: int = 28, canal_id: str | None = None) -> JSONResponse:
    dias = max(7, min(dias, 90))
    conta = _conta_do_canal(canal_id)
    try:
        serie = youtube_mod.obter_serie_diaria(conta, dias)
        atual = youtube_mod.obter_estatisticas_canal(conta)["inscritos"]
    except Exception as erro:
        return JSONResponse({"erro": str(erro)}, status_code=409)
    return JSONResponse({"serie": serie, "inscritos_atual": atual})


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
        ideias = agente.sugerir_ideias(canal.obter_contexto(), tendencias, titulos_existentes=[v["titulo"] for v in api_listar_videos()])
    except RuntimeError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=502)

    return JSONResponse({"ideias": ideias, "aviso": aviso_tendencias})


_RE_DATA_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_RE_HORA = re.compile(r"\d{2}:\d{2}")


def _aplicar_edicao_do_agente(pedido: dict) -> dict:
    """Aplica título/descrição/privacidade/tags/texto da thumbnail num vídeo,
    validando tudo contra o disco. Vídeo já publicado também é atualizado no
    YouTube (videos.update)."""
    slug = str(pedido.get("slug") or "")
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not slug or "/" in slug or "\\" in slug or not caminho_meta.exists():
        return {"acao": "erro", "resposta": f'Não achei nenhum vídeo "{slug}" pra editar — confira o título e tente de novo.'}

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    mudou = []
    titulo = str(pedido.get("titulo") or "").strip()[:100]
    if titulo and titulo != metadados.get("titulo"):
        metadados["titulo"] = titulo  # a pasta (slug) continua a mesma
        mudou.append("título")
    descricao = str(pedido.get("descricao_youtube") or "").strip()[:5000]
    if descricao:
        metadados["descricao_youtube"] = descricao
        mudou.append("descrição")
    if pedido.get("privacidade") in ("private", "unlisted", "public") and pedido["privacidade"] != metadados.get("privacidade"):
        metadados["privacidade"] = pedido["privacidade"]
        mudou.append("privacidade")
    tags = pedido.get("tags")
    if isinstance(tags, list) and tags:
        limpas = youtube_mod._tags_validas([str(t) for t in tags])
        if limpas:
            (pasta / "tags.txt").write_text(", ".join(limpas), encoding="utf-8")
            mudou.append("tags")
    texto_thumb = str(pedido.get("thumbnail_texto") or "").strip()[:80]
    if texto_thumb:
        metadados["thumbnail_texto"] = texto_thumb
        base = _base_valida_ou_erro(pasta)
        if not isinstance(base, JSONResponse):
            _rerenderizar_thumbnail(pasta, base, metadados)
        mudou.append("texto da thumbnail")
    if not mudou:
        return {"acao": "responder", "resposta": pedido.get("texto") or "Não entendi o que mudar nesse vídeo — pode dizer de outro jeito?"}

    caminho_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")
    resposta = f'Atualizei {", ".join(mudou)} de "{metadados.get("titulo", slug)}".'

    ids = [(metadados.get("youtube_video_id"), False), (metadados.get("youtube_short_id"), True)]
    if any(i for i, _ in ids) and set(mudou) & {"título", "descrição", "privacidade", "tags"}:
        from engine import agendador as agendador_mod
        tags_arq = pasta / "tags.txt"
        lista_tags = [t.strip() for t in tags_arq.read_text(encoding="utf-8").split(",")] if tags_arq.exists() else []
        roteiro_arq = pasta / "roteiro.txt"
        desc_final = metadados.get("descricao_youtube") or (roteiro_arq.read_text(encoding="utf-8") if roteiro_arq.exists() else metadados.get("titulo", ""))
        conta = agendador_mod._conta_youtube_do_video(metadados)
        try:
            for video_id, eh_short in ids:
                if video_id:
                    youtube_mod.atualizar_video(conta, video_id, metadados.get("titulo", slug), desc_final, lista_tags, metadados.get("privacidade") or "public", eh_short)
            resposta += " Também atualizado no YouTube."
        except Exception as erro:
            resposta += f" Mas não consegui atualizar no YouTube ({erro}). Se for erro de permissão, reconecte a conta na aba Canais e peça de novo."
    return {"acao": "editar", "resposta": resposta, "slug": slug}


AMOSTRAS_VOZ = {
    "pt-BR": "Você sabia que o polvo tem três corações? Incrível, não é? Agora vem a parte mais surpreendente!",
    "en-US": "Did you know that an octopus has three hearts? Amazing, right? Now comes the most surprising part!",
    "es-ES": "¿Sabías que el pulpo tiene tres corazones? ¡Increíble! Ahora viene la parte más sorprendente.",
    "fr-FR": "Saviez-vous que la pieuvre a trois cœurs ? Incroyable ! Voici la partie la plus surprenante.",
}


@app.get("/api/voz/amostra")
async def api_amostra_voz(voz: str = "mulher", idioma: str = "pt-BR"):
    """Amostra curta da voz escolhida (guardada em dados/amostras pra não sintetizar de novo)."""
    from fastapi.responses import FileResponse

    if idioma not in AMOSTRAS_VOZ or voz not in ("mulher", "homem", "crianca", "mulher_animada", "homem_animado"):
        return JSONResponse({"erro": "voz ou idioma inválido"}, status_code=400)
    arquivo = RAIZ_SAIDA.parent / "dados" / "amostras" / f"{idioma}_{voz}.mp3"
    if not arquivo.exists():
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(tts_mod.sintetizar, AMOSTRAS_VOZ[idioma], idioma, voz, arquivo)
        except Exception as erro:
            arquivo.unlink(missing_ok=True)
            return JSONResponse({"erro": f"não consegui gerar a amostra: {erro}"}, status_code=502)
    return FileResponse(arquivo, media_type="audio/mpeg")


@app.post("/api/agente/duracao")
def api_sugerir_duracao(titulo: str = Form(""), num_cenas: int | None = Form(None), descricao_video: str = Form("")) -> dict:
    """O agente recomenda quantos minutos esse tipo de vídeo deve ter neste canal (usado no botão "Sugerir" do Novo vídeo)."""
    existentes = [f'"{v["titulo"]}": {round(v["duracao_segundos"] / 60, 1)} min' for v in api_listar_videos() if v.get("duracao_segundos")][:15]
    try:
        return agente.sugerir_duracao(titulo.strip(), num_cenas, descricao_video.strip(), canal.obter_contexto(), existentes)
    except (RuntimeError, ValueError, KeyError, TypeError):
        minutos = round(max(1.0, (num_cenas or 3) * 0.6), 1)  # plano B sem IA: ~35 s por item
        return {"minutos": minutos, "motivo": "Estimativa simples (o agente não respondeu): cerca de 35 segundos por cena."}


@app.post("/api/agente/perguntar")
def api_agente_perguntar(mensagem: str = Form(...)) -> JSONResponse:
    """Campo livre do agente: responde perguntas/pede ideias, ou executa um
    comando simples reconhecido (por enquanto só reagendar um vídeo). Toda
    ação vinda do modelo é validada contra o estado real antes de aplicar —
    nunca confia cegamente no que ele disser."""
    mensagem = mensagem.strip()
    if not mensagem:
        return JSONResponse({"erro": "escreve alguma coisa pro agente"}, status_code=400)

    videos = api_listar_videos()
    for v in videos:  # o agente precisa "ver" cada vídeo: duração, cenas, formatos, começo do roteiro
        pasta_v = RAIZ_SAIDA / v["slug"]
        try:
            meta_v = json.loads((pasta_v / "metadata.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta_v = {}
        v["n_cenas"] = len(meta_v.get("cenas") or []) or "?"
        v["formatos"] = meta_v.get("formatos", "ambos")
        v["privacidade"] = meta_v.get("privacidade", "public")
        roteiro_v = pasta_v / "roteiro.txt"
        v["resumo"] = " ".join(roteiro_v.read_text(encoding="utf-8").split())[:160] if roteiro_v.exists() else ""
    try:
        resultado = agente.responder_livre(mensagem, canal.obter_contexto(), videos)
    except RuntimeError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=502)

    if resultado.get("acao") == "cancelar":
        slug = str(resultado.get("slug") or "")
        titulo_video = next((v["titulo"] for v in videos if v["slug"] == slug), slug)
        if not _excluir_video(slug):
            return JSONResponse({"acao": "erro", "resposta": f'Não achei nenhum vídeo "{slug}" pra cancelar — confira o título e tente de novo.'})
        return JSONResponse({"acao": "cancelar", "resposta": f'Cancelei e apaguei "{titulo_video}" da fila — não será publicado.', "slug": slug})

    if resultado.get("acao") == "editar":
        return JSONResponse(_aplicar_edicao_do_agente(resultado))

    if resultado.get("acao") != "reagendar":
        return JSONResponse({"acao": "responder", "resposta": resultado.get("texto", "")})

    slug = str(resultado.get("slug") or "")
    data_postagem = str(resultado.get("data_postagem") or "")
    hora_postagem = resultado.get("hora_postagem")
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"

    if not slug or not caminho_meta.exists():
        return JSONResponse({"acao": "erro", "resposta": f'Não achei nenhum vídeo "{slug}" pra reagendar — confira o título e tente de novo.'})
    if not _RE_DATA_ISO.fullmatch(data_postagem):
        return JSONResponse({"acao": "erro", "resposta": "Não entendi pra qual data reagendar — pode repetir com uma data mais clara?"})
    if hora_postagem and not _RE_HORA.fullmatch(str(hora_postagem)):
        hora_postagem = None

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    metadados["data_postagem"] = data_postagem
    if hora_postagem:
        metadados["hora_postagem"] = hora_postagem
    else:
        metadados.pop("hora_postagem", None)
    caminho_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")

    return JSONResponse(
        {
            "acao": "reagendar",
            "resposta": resultado.get("texto") or f"Reagendado \"{metadados.get('titulo', slug)}\" pra {data_postagem}.",
            "slug": slug,
            "data_postagem": data_postagem,
            "hora_postagem": hora_postagem,
        }
    )


# ---------------------------------------------------------------------------
# biblioteca: áudios e imagens importados por você, reutilizáveis em qualquer vídeo
# ---------------------------------------------------------------------------

TAMANHO_MAX_BIBLIOTECA_BYTES = 40 * 1024 * 1024


def _meta_biblioteca() -> dict:
    caminho = biblioteca.RAIZ / "meta.json"
    try:
        return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _usos_biblioteca() -> dict:
    """{("audios"|"imagens", nome): [títulos dos vídeos que usam]} — lido dos metadados de cada vídeo."""
    usos: dict = {}
    if not RAIZ_SAIDA.exists():
        return usos
    for pasta in RAIZ_SAIDA.iterdir():
        caminho_meta = pasta / "metadata.json"
        if not caminho_meta.exists():
            continue
        try:
            meta = json.loads(caminho_meta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        titulo = meta.get("titulo", pasta.name)
        nomes_som = [i["nome"] for i in (meta.get("som_fundo_playlist") or [])] or ([meta["som_fundo_biblioteca"]] if meta.get("som_fundo_biblioteca") else [])
        for nome_som in nomes_som:
            if titulo not in usos.setdefault(("audios", nome_som), []):
                usos[("audios", nome_som)].append(titulo)
        for nome_vid in (meta.get("videos_base_cenas") or {}).values():
            if titulo not in usos.setdefault(("videos", nome_vid), []):
                usos[("videos", nome_vid)].append(titulo)
        for nome_img in (meta.get("imagens_base_cenas") or {}).values():
            if titulo not in usos.setdefault(("imagens", nome_img), []):
                usos[("imagens", nome_img)].append(titulo)
        fonte = pasta / "thumbnail_fonte.txt"
        if fonte.exists():
            nome_fonte = fonte.read_text(encoding="utf-8").strip()
            if nome_fonte.startswith("biblioteca-"):
                lista = usos.setdefault(("imagens", nome_fonte[len("biblioteca-"):]), [])
                if titulo not in lista:
                    lista.append(titulo)
    return usos


def _atribuir_canal_ativo(tipo: str, nome: str) -> None:
    """Item recém-importado fica no canal ativo (só aparece nele); dá pra compartilhar com todos na aba Base."""
    meta = _meta_biblioteca()
    item = meta.setdefault(tipo, {}).setdefault(nome, {})
    item["canal_id"] = canal.canal_ativo_id()
    biblioteca.RAIZ.mkdir(parents=True, exist_ok=True)
    (biblioteca.RAIZ / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/api/biblioteca")
def api_listar_biblioteca(canal: str = "") -> dict:
    """?canal=ID devolve só o que é desse canal + o que é compartilhado (sem canal). Sem o parâmetro, tudo."""
    meta, usos = _meta_biblioteca(), _usos_biblioteca()
    do_canal = lambda item: not canal or item["canal_id"] in ("", canal)  # noqa: E731

    def info(tipo: str, nome: str, url: str) -> dict:
        extra = (meta.get(tipo) or {}).get(nome, {})
        return {
            "nome": nome, "url": url,
            "descricao": extra.get("descricao", ""), "canal_id": extra.get("canal_id", ""),
            "usado_em": usos.get((tipo, nome), []),
        }

    audios = [{**i, "duracao_segundos": biblioteca.duracao_de(biblioteca.PASTA_AUDIOS / i["nome"])}
              for i in (info("audios", n, f"/biblioteca/audios/{n}") for n in biblioteca.listar_audios()) if do_canal(i)]
    return {
        "audios": [a["url"] for a in audios],
        "audios_nomes": [a["nome"] for a in audios],
        "audios_info": audios,
        "imagens": [i for i in (info("imagens", n, f"/biblioteca/imagens/{n}") for n in biblioteca.listar_imagens()) if do_canal(i)],
        "videos": [i for i in (info("videos", n, f"/biblioteca/videos/{n}") for n in biblioteca.listar_videos()) if do_canal(i)],
        "canais": [{"id": c["id"], "nome": c["nome"]} for c in canais_mod.listar_canais()],
        "canal_ativo": canais_mod.canal_ativo_id(),
    }


@app.put("/api/biblioteca/{tipo}/{nome}/info")
def api_info_biblioteca(tipo: str, nome: str, descricao: str = Form(""), canal_id: str = Form("")) -> dict:
    """Descrição e canal de um item da Base (só metadado, não mexe no arquivo)."""
    existentes = {"audios": biblioteca.listar_audios, "imagens": biblioteca.listar_imagens, "videos": biblioteca.listar_videos}.get(tipo, lambda: None)()
    if existentes is None or nome not in existentes:
        return JSONResponse({"erro": "item não encontrado"}, status_code=404)
    meta = _meta_biblioteca()
    meta.setdefault(tipo, {})[nome] = {"descricao": descricao.strip()[:300], "canal_id": canal_id.strip()[:80]}
    biblioteca.RAIZ.mkdir(parents=True, exist_ok=True)
    (biblioteca.RAIZ / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@app.post("/api/biblioteca/audios/upload")
async def api_upload_audio_biblioteca(arquivo: UploadFile = File(...)) -> JSONResponse:
    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAX_BIBLIOTECA_BYTES:
        return JSONResponse({"erro": "arquivo maior que 40MB"}, status_code=400)
    try:
        nome = biblioteca.salvar_audio(arquivo.filename or "audio", conteudo)
    except ValueError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=400)
    _atribuir_canal_ativo("audios", nome)
    return JSONResponse({"nome": nome, "url": f"/biblioteca/audios/{nome}"})


@app.delete("/api/biblioteca/audios/{nome}")
def api_remover_audio_biblioteca(nome: str) -> JSONResponse:
    if not biblioteca.remover_audio(Path(nome).name):
        return JSONResponse({"erro": "áudio não encontrado"}, status_code=404)
    return JSONResponse({"ok": True})


@app.post("/api/biblioteca/videos/upload")
async def api_upload_video_biblioteca(arquivo: UploadFile = File(...)) -> JSONResponse:
    """Vídeo (com ou sem áudio) pra usar numa cena. É reencodado pra mp4 e o áudio dele NÃO entra no
    vídeo final: a narração continua sendo o áudio."""
    conteudo = await arquivo.read()
    try:
        nome = await asyncio.to_thread(biblioteca.salvar_video, arquivo.filename or "video", conteudo)
    except ValueError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=400)
    _atribuir_canal_ativo("videos", nome)
    return JSONResponse({"nome": nome, "url": f"/biblioteca/videos/{nome}"})


@app.delete("/api/biblioteca/videos/{nome}")
def api_remover_video_biblioteca(nome: str) -> JSONResponse:
    if not biblioteca.remover_video(nome):
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)
    return JSONResponse({"ok": True})


@app.post("/api/videos/{slug}/cenas/{indice}/video-base")
def api_video_da_base_na_cena(slug: str, indice: int, nome: str = Form(...)) -> dict:
    """Coloca um vídeo da Base numa cena (cortado pro formato, em loop se for curto, sem o áudio dele)."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if "/" in slug or "\\" in slug or not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)
    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    if not (0 <= indice < len(metadados.get("cenas") or [])):
        return JSONResponse({"erro": "cena não existe"}, status_code=404)
    origem = biblioteca.caminho_video_valido(nome)
    if origem is None:
        return JSONResponse({"erro": "vídeo da Base inválido"}, status_code=400)
    _marcar_imagem_base_da_cena(caminho_meta, indice, None, video=origem.name)
    job = jobs.criar_job_cena(metadados.get("titulo", slug), slug, indice, video_proprio=origem)
    return {"job_id": job.id}


@app.post("/api/biblioteca/imagens/upload")
async def api_upload_imagem_biblioteca(arquivo: UploadFile = File(...)) -> JSONResponse:
    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAX_BIBLIOTECA_BYTES:
        return JSONResponse({"erro": "arquivo maior que 40MB"}, status_code=400)
    try:
        nome = biblioteca.salvar_imagem(arquivo.filename or "imagem", conteudo)
    except Exception:
        return JSONResponse({"erro": "não consegui abrir esse arquivo como imagem"}, status_code=400)
    _atribuir_canal_ativo("imagens", nome)
    return JSONResponse({"nome": nome, "url": f"/biblioteca/imagens/{nome}"})


@app.delete("/api/biblioteca/imagens/{nome}")
def api_remover_imagem_biblioteca(nome: str) -> JSONResponse:
    if not biblioteca.remover_imagem(Path(nome).name):
        return JSONResponse({"erro": "imagem não encontrada"}, status_code=404)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# afiliados: lista de produtos/links pra divulgar (ideia guardada, ainda sem
# inserção automática nos vídeos)
# ---------------------------------------------------------------------------

ARQUIVO_ANOTACOES = RAIZ_SAIDA.parent / "dados" / "anotacoes.txt"


@app.get("/api/anotacoes")
def api_ler_anotacoes() -> dict:
    return {"texto": ARQUIVO_ANOTACOES.read_text(encoding="utf-8") if ARQUIVO_ANOTACOES.exists() else ""}


@app.put("/api/anotacoes")
def api_salvar_anotacoes(texto: str = Form("")) -> dict:
    ARQUIVO_ANOTACOES.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO_ANOTACOES.write_text(texto[:200000], encoding="utf-8")
    return {"ok": True}


@app.get("/api/afiliados")
def api_listar_afiliados() -> list[dict]:
    return afiliados.listar()


@app.post("/api/afiliados")
def api_adicionar_afiliado(
    nome: str = Form(...),
    plataforma: str = Form("outro"),
    link: str = Form(""),
    nota: str = Form(""),
) -> JSONResponse:
    nome = nome.strip()
    if not nome:
        return JSONResponse({"erro": "dê um nome pro produto"}, status_code=400)
    item = afiliados.adicionar(nome, plataforma, link, nota)
    return JSONResponse(item)


@app.delete("/api/afiliados/{item_id}")
def api_remover_afiliado(item_id: str) -> JSONResponse:
    if not afiliados.remover(item_id):
        return JSONResponse({"erro": "não encontrado"}, status_code=404)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# pré-visualização do roteiro (antes de gerar o vídeo inteiro)
# ---------------------------------------------------------------------------

@app.post("/api/estimativa")
def api_estimativa(
    duracao_alvo: float | None = Form(None), num_cenas: int | None = Form(None), imagem: str = Form("ia"),
    formatos: str = Form("ambos"), sem_narracao: bool = Form(False), tem_roteiro: bool = Form(False),
    narracao_propria: bool = Form(False), som_fundo: bool = Form(False), transicao: str = Form("fade"),
    n_imagens_base: int = Form(0),
) -> dict:
    """Quanto tempo esse vídeo deve levar pra ficar pronto (mostrado no Novo vídeo enquanto você escolhe)."""
    segundos = estimativa_mod.estimar({
        "duracao_min": duracao_alvo, "n_cenas": num_cenas, "estilo_imagem": imagem, "formatos": formatos,
        "sem_narracao": sem_narracao, "tem_roteiro": tem_roteiro, "narracao_propria": narracao_propria,
        "som_fundo": som_fundo, "transicao": transicao, "n_imagens_base": n_imagens_base,
    })
    return {"segundos": int(segundos)}


@app.post("/api/roteiro/preview")
def api_preview_roteiro(
    titulo: str = Form(...),
    duracao_alvo: float | None = Form(None),
    descricao_video: str = Form(""),
    num_cenas: int | None = Form(None),
    midias: str = Form(""),
) -> JSONResponse:
    try:
        roteiro = roteiro_mod.gerar_roteiro(
            titulo.strip(),
            duracao_alvo or 1.0,
            contexto_canal=canal.obter_contexto(),
            descricao_video=descricao_video.strip(),
            num_cenas=num_cenas if num_cenas and 1 < num_cenas <= 40 else None,
            cenas_midia=midias_mod.descricoes_para_roteiro([m for m in midias.split("|") if m.strip()]) or None,
        )
        return JSONResponse({"roteiro": roteiro})
    except RuntimeError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=502)


# ---------------------------------------------------------------------------
# geração de vídeo
# ---------------------------------------------------------------------------

def _palavras(titulo: str) -> set:
    return set(re.findall(r"\w+", titulo.casefold()))


def _titulo_parecido(titulo: str) -> str | None:
    """Título de um vídeo existente que seja igual (mesma pasta) ou muito
    parecido (>= 70% das palavras em comum), pra avisar antes de repetir."""
    novo = _palavras(titulo)
    for v in api_listar_videos():
        if v["slug"] == slug_titulo(titulo):
            return v["titulo"]
        velho = _palavras(v["titulo"])
        if novo and velho and len(novo & velho) / len(novo | velho) >= 0.7:
            return v["titulo"]
    return None


@app.post("/api/videos")
def api_criar_video(
    titulo: str = Form(...),
    data_postagem: str = Form(...),
    hora_postagem: str = Form(""),
    roteiro: str = Form(""),
    descricao_video: str = Form(""),
    idioma: str = Form("pt-BR"),
    voz: str = Form("mulher"),
    imagem: str = Form("procedural"),
    duracao_alvo: float | None = Form(None),
    sem_narracao: bool = Form(False),
    som_fundo_tipo: str = Form(""),
    som_fundo_descricao: str = Form(""),
    som_fundo_biblioteca: str = Form(""),
    som_fundo_playlist: str = Form(""),
    som_fundo_repetir: str = Form("repetir"),
    som_fundo_suave: bool = Form(False),
    som_fundo_fade: bool = Form(False),
    privacidade: str = Form("public"),
    formatos: str = Form("ambos"),
    num_cenas: int | None = Form(None),
    imagens_base: str = Form(""),
    base_restante: str = Form("estilo"),
    transicao: str = Form("fade"),
    legenda_modo: str = Form("karaoke"),
    legenda_tamanho: str = Form("m"),
    legenda_posicao: str = Form("baixo"),
    legenda_cor: str = Form(""),
    legenda_caixa: bool = Form(False),
    legenda_fundo: str = Form(""),
    confirmar_duplicado: bool = Form(False),
    narracao_audio: UploadFile | None = File(None),
) -> dict:
    titulo = titulo.strip()
    if privacidade not in ("private", "unlisted", "public"):
        privacidade = "public"

    if not confirmar_duplicado:
        parecido = _titulo_parecido(titulo)
        if parecido:
            return JSONResponse(
                {"erro": f'Já existe um vídeo igual ou muito parecido: "{parecido}". Gerar mesmo assim? (título igual sobrescreve o anterior)', "duplicado": True},
                status_code=409,
            )
    playlist_som = []
    try:
        for item in json.loads(som_fundo_playlist) if som_fundo_playlist.strip() else []:
            if biblioteca.caminho_audio_valido(str(item.get("nome", ""))):
                seg = item.get("segundos")
                playlist_som.append({"nome": item["nome"], "segundos": float(seg) if seg else None})
    except (ValueError, AttributeError, TypeError):
        playlist_som = []
    roteiro_limpo = roteiro.strip()
    narracao_customizada = False

    if narracao_audio is not None and narracao_audio.filename and not sem_narracao:
        if not roteiro_limpo:
            return JSONResponse(
                {"erro": "com narração gravada/enviada, cole no campo Roteiro exatamente o texto que você leu antes de enviar"},
                status_code=400,
            )
        conteudo = narracao_audio.file.read()
        if len(conteudo) > TAMANHO_MAX_BIBLIOTECA_BYTES:
            return JSONResponse({"erro": "áudio de narração maior que 40MB"}, status_code=400)
        pasta = RAIZ_SAIDA / slug_titulo(titulo)
        pasta.mkdir(parents=True, exist_ok=True)
        try:
            tts_mod.salvar_narracao_customizada(conteudo, pasta / "narracao_custom.mp3")
        except ValueError as erro:
            return JSONResponse({"erro": str(erro)}, status_code=400)
        narracao_customizada = True

    params = dict(
        titulo=titulo,
        roteiro=None if sem_narracao else (roteiro_limpo or None),
        idioma=idioma,
        voz=voz,
        estilo_imagem=imagem,
        duracao_alvo_minutos=duracao_alvo,
        descricao_video=descricao_video.strip(),
        data_postagem=data_postagem,
        hora_postagem=hora_postagem.strip() or None,
        sem_narracao=sem_narracao,
        som_fundo_tipo=som_fundo_tipo,
        som_fundo_descricao=som_fundo_descricao.strip(),
        som_fundo_biblioteca=(playlist_som[0]["nome"] if playlist_som else som_fundo_biblioteca.strip()),
        som_fundo_playlist=playlist_som,
        som_fundo_opcoes={"repetir": "silencio" if som_fundo_repetir == "silencio" else "repetir", "suave": som_fundo_suave, "fade": som_fundo_fade},
        narracao_customizada=narracao_customizada,
        privacidade=privacidade,
        formatos=formatos if formatos in ("ambos", "normal", "shorts") else "ambos",
        num_cenas=num_cenas if num_cenas and 1 <= num_cenas <= 40 else None,
        imagens_base=[n for n in imagens_base.split("|") if n.strip()],
        base_restante=base_restante if base_restante in ("estilo", "repetir") else "estilo",
        transicao=transicao if transicao in render_mod.TRANSICOES else "fade",
        legenda=_config_legenda(legenda_modo, legenda_tamanho, legenda_posicao, legenda_cor, legenda_caixa, legenda_fundo),
        canal_id=canal.canal_ativo_id(),  # vídeo pertence ao canal ativo no momento em que foi criado
    )

    job = jobs.criar_job(titulo, params)
    return {"job_id": job.id}


@app.post("/api/videos/{slug}/editado")
def api_editado(slug: str, editado: bool = Form(...)) -> dict:
    """Marca (ou desmarca) que você já editou/revisou esse vídeo. Só vídeo "editado" pode ter a publicação confirmada."""
    caminho_meta = RAIZ_SAIDA / slug / "metadata.json"
    if "/" in slug or "\\" in slug or not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)
    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    if metadados.get("publicado"):
        return JSONResponse({"erro": "esse vídeo já foi publicado"}, status_code=409)
    metadados["editado"] = editado
    if not editado:
        metadados["aprovado"] = False  # sem "editado" não fica confirmado
    caminho_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "editado": editado}


@app.post("/api/videos/{slug}/aprovacao")
def api_aprovacao(slug: str, aprovado: bool = Form(...)) -> dict:
    """Confirma (ou desfaz a confirmação de) publicação. Sem confirmar, o agendador nunca sobe o vídeo."""
    caminho_meta = RAIZ_SAIDA / slug / "metadata.json"
    if "/" in slug or "\\" in slug or not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)
    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    if metadados.get("publicado"):
        return JSONResponse({"erro": "esse vídeo já foi publicado"}, status_code=409)
    if aprovado and not metadados.get("editado"):
        return JSONResponse({"erro": 'marque a caixinha "Editado" antes de confirmar a publicação'}, status_code=409)
    metadados["aprovado"] = aprovado
    if aprovado:
        metadados.pop("publicacao_erro", None)
    caminho_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "aprovado": aprovado}


def _config_legenda(modo: str, tamanho: str, posicao: str, cor: str, caixa: bool, fundo: str = "") -> dict:
    return subtitles_mod.normalizar_config({
        "modo": modo if modo in ("karaoke", "simples", "nenhuma") else "karaoke",
        "tamanho": tamanho if tamanho in ("p", "m", "g") else "m",
        "posicao": posicao if posicao in ("baixo", "meio", "topo") else "baixo",
        "cor": cor,
        "fundo": fundo if fundo in subtitles_mod.FUNDOS_LEGENDA else ("caixa" if caixa else "contorno"),
    })


@app.post("/api/videos/{slug}/legenda")
def api_legenda(
    slug: str,
    modo: str = Form("karaoke"), tamanho: str = Form("m"), posicao: str = Form("baixo"),
    cor: str = Form(""), caixa: bool = Form(True), transicao: str = Form(""), fundo: str = Form(""),
) -> dict:
    """Muda o estilo da legenda (e opcionalmente a transição) e remonta os vídeos — sem refazer imagens/narração."""
    caminho_meta = RAIZ_SAIDA / slug / "metadata.json"
    if "/" in slug or "\\" in slug or not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)
    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    if metadados.get("publicado"):
        return JSONResponse({"erro": "esse vídeo já foi publicado"}, status_code=409)
    if transicao in render_mod.TRANSICOES:
        metadados["transicao"] = transicao
        caminho_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")
    config = _config_legenda(modo, tamanho, posicao, cor, caixa, fundo)
    job = jobs.criar_job_funcao(metadados.get("titulo", slug), lambda cb: _resultado_videos(slug, pipeline_mod.regenerar_legenda(slug, config, progresso=cb)))
    return {"job_id": job.id}


def _resultado_videos(slug: str, r: dict) -> dict:
    marca = int(time.time())
    return {
        "slug": slug,
        "video_16_9": f"/videos/{slug}/{r['video_16_9']}?v={marca}" if r.get("video_16_9") else None,
        "video_9_16": f"/videos/{slug}/{r['video_9_16']}?v={marca}" if r.get("video_9_16") else None,
    }


@app.post("/api/videos/{slug}/regenerar")
def api_regenerar_video(slug: str, manter_roteiro: bool = Form(True), reaproveitar_imagens: bool = Form(False)) -> dict:
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
        hora_postagem=metadados.get("hora_postagem"),
        sem_narracao=sem_narracao,
        som_fundo_tipo=metadados.get("som_fundo_tipo", ""),
        som_fundo_descricao=metadados.get("som_fundo_descricao", ""),
        som_fundo_biblioteca=metadados.get("som_fundo_biblioteca", ""),
        som_fundo_playlist=metadados.get("som_fundo_playlist") or [],
        som_fundo_opcoes=metadados.get("som_fundo_opcoes") or {},
        narracao_customizada=metadados.get("narracao_customizada", False),
        privacidade=metadados.get("privacidade", "public"),
        formatos=metadados.get("formatos", "ambos"),
        num_cenas=metadados.get("num_cenas"),
        imagens_base=metadados.get("imagens_base") or [],
        base_restante=metadados.get("base_restante", "estilo"),
        transicao=metadados.get("transicao", "fade"),
        legenda=metadados.get("legenda") or None,
        reaproveitar_imagens=reaproveitar_imagens,
        canal_id=metadados.get("canal_id"),  # mantém o canal original do vídeo, não o ativo agora
    )

    job = jobs.criar_job(titulo, params)
    return {"job_id": job.id}


def _excluir_video(slug: str) -> bool:
    """Apaga a pasta do vídeo (nunca publica). Só aceita um nome de pasta que
    existe de verdade em output/ e tem metadata.json — nada de caminho livre."""
    pasta = RAIZ_SAIDA / Path(slug).name
    if not slug or Path(slug).name != slug or not (pasta / "metadata.json").exists():
        return False
    shutil.rmtree(pasta)
    return True


@app.delete("/api/videos/{slug}")
def api_excluir_video(slug: str) -> JSONResponse:
    if not _excluir_video(slug):
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)
    return JSONResponse({"ok": True})


@app.post("/api/videos/{slug}/agendamento")
def api_editar_agendamento(slug: str, data_postagem: str = Form(...), hora_postagem: str = Form("")) -> dict:
    """Só reagenda (data/hora de postagem) sem regenerar nada — pra corrigir
    rapidinho quando o plano de publicação muda."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    metadados["data_postagem"] = data_postagem
    if hora_postagem.strip():
        metadados["hora_postagem"] = hora_postagem.strip()
    else:
        metadados.pop("hora_postagem", None)
    caminho_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "data_postagem": data_postagem, "hora_postagem": metadados.get("hora_postagem")}


def _thumbnail_base_url(pasta: Path) -> str | None:
    """URL da imagem de cena usada como fundo da thumbnail atual (sem o
    texto/overlay desenhado) — usada pra arrastar o texto em cima dela."""
    fonte_txt = pasta / "thumbnail_fonte.txt"
    nome = fonte_txt.read_text(encoding="utf-8").strip() if fonte_txt.exists() else "cena00_16x9.png"
    caminho = pasta / nome
    if not caminho.exists():
        candidatas = sorted(pasta.glob("cena*_16x9.png"))
        if not candidatas:
            return None
        caminho = candidatas[0]
    return f"/videos/{pasta.name}/{caminho.name}?v={int(caminho.stat().st_mtime)}"


def _pos_livre_de(metadados: dict) -> tuple | None:
    """(fracao_x, fracao_y) salvos de um arraste, ou None se a thumbnail usa a
    grade de 9 pontos (thumbnail_posicao) — arrastar sempre tem prioridade
    sobre a grade quando os dois estão salvos."""
    x, y = metadados.get("thumbnail_pos_x"), metadados.get("thumbnail_pos_y")
    return (x, y) if isinstance(x, (int, float)) and isinstance(y, (int, float)) else None


def _tamanho_fonte_de(metadados: dict) -> int:
    """Tamanho em pixels: usa o valor livre salvo (thumbnail_tamanho_px, do
    controle deslizante) se existir; senão cai pro preset antigo
    (pequeno/médio/grande) de thumbnails salvas antes desse controle existir."""
    px = metadados.get("thumbnail_tamanho_px")
    if isinstance(px, (int, float)) and px:
        return int(px)
    return thumbnail_mod.TAMANHOS.get(metadados.get("thumbnail_tamanho", "medio"), 80)


def _status_de(metadados: dict) -> str:
    """Status resumido pra fila: publicado / erro / pronto (dia já chegou,
    esperando o agendador ou o próximo publicar manual) / aguardando (ainda
    não chegou a data)."""
    if metadados.get("publicado"):
        return "publicado"
    if metadados.get("publicacao_erro"):
        return "erro"
    if not metadados.get("aprovado", False):
        return "revisar"  # gerado, mas ainda sem a sua confirmação de publicação
    data_postagem = metadados.get("data_postagem")
    if not data_postagem:
        return "aguardando"
    agora = datetime.now()
    hoje = agora.date().isoformat()
    if data_postagem > hoje:
        return "aguardando"
    hora_postagem = metadados.get("hora_postagem")
    if data_postagem == hoje and hora_postagem and agora.strftime("%H:%M") < hora_postagem:
        return "aguardando"
    return "pronto"


def _base_valida_ou_erro(pasta: Path) -> Path | JSONResponse:
    """Imagem de cena/custom atualmente usada como base, ou um erro se a
    pasta não tiver nenhuma."""
    fonte_txt = pasta / "thumbnail_fonte.txt"
    fonte_nome = fonte_txt.read_text(encoding="utf-8").strip() if fonte_txt.exists() else "cena00_16x9.png"
    base = pasta / fonte_nome
    if base.exists():
        return base
    candidatas = sorted(pasta.glob("cena*_16x9.png"))
    if not candidatas:
        return JSONResponse({"erro": "não achei nenhuma imagem de cena pra usar de base"}, status_code=404)
    return candidatas[0]


def _rerenderizar_thumbnail(pasta: Path, base: Path, metadados: dict) -> None:
    texto = metadados.get("thumbnail_texto") or metadados.get("titulo", pasta.name)
    cor = thumbnail_mod.cor_de_hex(metadados.get("thumbnail_cor", ""))
    posicao = metadados.get("thumbnail_posicao", "baixo-centro")
    thumbnail_mod.gerar_thumbnail(base, texto, pasta / "thumbnail.png", cor, posicao, _tamanho_fonte_de(metadados), _pos_livre_de(metadados), efeito=metadados.get("thumbnail_efeito", "nenhum"))


@app.get("/api/videos/{slug}/thumbnail/imagens")
def api_listar_imagens_thumbnail(slug: str) -> dict:
    """Todas as imagens de cena (+ a customizada enviada, se houver) que dá
    pra escolher como base da thumbnail, pra mostrar uma galeria pra clicar
    em vez de só sortear aleatoriamente."""
    pasta = RAIZ_SAIDA / slug
    if not pasta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    fonte_txt = pasta / "thumbnail_fonte.txt"
    atual = fonte_txt.read_text(encoding="utf-8").strip() if fonte_txt.exists() else "cena00_16x9.png"

    candidatas = sorted(pasta.glob("cena*_16x9.png"))
    custom = pasta / "thumbnail_custom.png"
    if custom.exists():
        candidatas.append(custom)

    imagens = [
        {"nome": c.name, "url": f"/videos/{slug}/{c.name}?v={int(c.stat().st_mtime)}", "atual": c.name == atual}
        for c in candidatas
    ]
    # imagens importadas na Base também podem virar fundo de thumbnail —
    # identificadas com o prefixo "biblioteca:" pra distinguir de cenas locais
    descricoes = (_meta_biblioteca().get("imagens") or {})
    imagens += [
        {"nome": f"biblioteca:{nome}", "url": f"/biblioteca/imagens/{nome}", "atual": f"biblioteca-{nome}" == atual,
         "descricao": (descricoes.get(nome) or {}).get("descricao", "")}
        for nome in biblioteca.listar_imagens()
    ]
    return {"imagens": imagens}


@app.post("/api/videos/{slug}/thumbnail/escolher-imagem")
def api_escolher_imagem_thumbnail(slug: str, imagem: str = Form(...)) -> dict:
    """Troca a imagem de base da thumbnail pra uma cena específica (em vez de
    sortear) ou pra imagem customizada já enviada."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    if imagem.startswith("biblioteca:"):
        # imagem da Base: valida contra o que existe de verdade na biblioteca
        # (nunca um caminho arbitrário) e copia pra dentro da pasta do vídeo,
        # assim o resto do fluxo (thumbnail_fonte.txt etc.) funciona igual
        origem = biblioteca.caminho_imagem_valida(imagem[len("biblioteca:"):])
        if origem is None:
            return JSONResponse({"erro": "imagem inválida"}, status_code=400)
        nome = f"biblioteca-{origem.name}"
        shutil.copyfile(origem, pasta / nome)
    else:
        # só aceita nomes que já existem de verdade na pasta do vídeo (cena*_16x9.png
        # ou a customizada) — nunca um caminho arbitrário vindo do cliente
        nome = Path(imagem).name
        validos = {c.name for c in pasta.glob("cena*_16x9.png")}
        custom = pasta / "thumbnail_custom.png"
        if custom.exists():
            validos.add(custom.name)
        if nome not in validos:
            return JSONResponse({"erro": "imagem inválida"}, status_code=400)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    _rerenderizar_thumbnail(pasta, pasta / nome, metadados)
    (pasta / "thumbnail_fonte.txt").write_text(nome, encoding="utf-8")

    return {"thumbnail": f"/videos/{slug}/thumbnail.png?v={int(time.time())}", "thumbnail_base": _thumbnail_base_url(pasta)}


TAMANHO_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB, só sanidade


@app.post("/api/videos/{slug}/thumbnail/upload")
async def api_upload_imagem_thumbnail(slug: str, arquivo: UploadFile = File(...)) -> dict:
    """Sobe uma imagem sua (ex: uma foto real, um design pronto) pra usar
    como base da thumbnail, no lugar de uma cena gerada."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAX_UPLOAD_BYTES:
        return JSONResponse({"erro": "arquivo maior que 20MB"}, status_code=400)

    try:
        imagem = Image.open(io.BytesIO(conteudo))
        imagem.load()  # decodifica agora — detecta arquivo corrompido ou que não é imagem de verdade
        imagem = imagem.convert("RGB")
    except Exception:
        return JSONResponse({"erro": "não consegui abrir esse arquivo como imagem"}, status_code=400)

    caminho_base = pasta / "thumbnail_custom.png"
    imagem.save(caminho_base, "PNG")

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    _rerenderizar_thumbnail(pasta, caminho_base, metadados)
    (pasta / "thumbnail_fonte.txt").write_text(caminho_base.name, encoding="utf-8")

    return {"thumbnail": f"/videos/{slug}/thumbnail.png?v={int(time.time())}", "thumbnail_base": _thumbnail_base_url(pasta)}


@app.post("/api/videos/{slug}/thumbnail/editar")
def api_editar_thumbnail(
    slug: str,
    texto: str = Form(...),
    cor: str = Form(""),
    posicao: str = Form("baixo-centro"),
    tamanho_px: int = Form(80),
    pos_x: float | None = Form(None),
    pos_y: float | None = Form(None),
    efeito: str = Form("nenhum"),
) -> dict:
    """Troca o texto, a cor, o tamanho (em pixels, controle deslizante) e a
    posição da thumbnail (grade de 9 pontos OU arrastar livre — se pos_x/pos_y
    vierem preenchidos, arrastar manda e some com a grade), mantendo a mesma
    imagem de base atual. Fica salvo pro vídeo (sobrevive a "nova thumbnail" e
    a regenerar a cena 0) até você editar de novo."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    texto = texto.strip()
    if not texto:
        return JSONResponse({"erro": "o texto da thumbnail não pode ficar vazio"}, status_code=400)

    base = _base_valida_ou_erro(pasta)
    if isinstance(base, JSONResponse):
        return base

    cor_rgb = thumbnail_mod.cor_de_hex(cor)
    posicao = posicao if posicao in thumbnail_mod.POSICOES else "baixo-centro"
    tamanho_px = max(thumbnail_mod.TAMANHO_FONTE_MIN, min(thumbnail_mod.TAMANHO_FONTE_MAX, tamanho_px))
    pos_livre = (pos_x, pos_y) if pos_x is not None and pos_y is not None else None
    thumbnail_mod.gerar_thumbnail(base, texto, pasta / "thumbnail.png", cor_rgb, posicao, tamanho_px, pos_livre, efeito=efeito if efeito in thumbnail_mod.EFEITOS else "nenhum")

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    metadados["thumbnail_efeito"] = efeito if efeito in thumbnail_mod.EFEITOS else "nenhum"
    metadados["thumbnail_texto"] = texto
    metadados["thumbnail_cor"] = cor.strip().lstrip("#") if cor_rgb else ""
    metadados["thumbnail_posicao"] = posicao
    if pos_livre is not None:
        metadados["thumbnail_pos_x"], metadados["thumbnail_pos_y"] = pos_livre
    else:
        metadados.pop("thumbnail_pos_x", None)
        metadados.pop("thumbnail_pos_y", None)
    metadados["thumbnail_tamanho_px"] = tamanho_px
    metadados.pop("thumbnail_tamanho", None)
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

    def _url(i: int, sufixo: str) -> str | None:
        caminho = pasta / f"cena{i:02d}_{sufixo}.png"
        return f"/videos/{slug}/cena{i:02d}_{sufixo}.png?v={int(caminho.stat().st_mtime)}" if caminho.exists() else None

    resultado = []
    acumulado = 0.0
    for i, cena in enumerate(cenas):
        duracao = cena.get("duracao_segundos", 0) or 0
        resultado.append(
            {
                "indice": i,
                "texto": cena.get("texto", ""),
                "duracao_segundos": duracao,
                "duracao_natural_segundos": cena.get("duracao_natural", duracao),
                "duracao_minima_segundos": max(1.0, round(cena.get("duracao_natural", duracao) / pipeline_mod.VELOCIDADE_MAXIMA_FALA + 0.05, 1)),
                "inicio_segundos": round(acumulado, 1),
                "imagem": _url(i, "16x9"),
                "imagem_vertical": _url(i, "9x16"),
                "imagem_base": (metadados.get("imagens_base_cenas") or {}).get(str(i)),
                "video_base": (metadados.get("videos_base_cenas") or {}).get(str(i)),
                "descricao_imagem": (metadados.get("descricoes_cenas") or {}).get(str(i), ""),
            }
        )
        acumulado += duracao
    tempo_editavel = not metadados.get("sem_narracao") and (pasta / "cues.json").exists() and bool(metadados.get("narracao_arquivo") or (pasta / "narracao.mp3").exists())
    return {"cenas": resultado, "tempo_editavel": tempo_editavel}


@app.post("/api/videos/{slug}/cenas/{indice}/regenerar")
def api_regenerar_cena(slug: str, indice: int, descricao: str | None = Form(None)) -> dict:
    """Refaz só a imagem de uma cena e remonta o vídeo — não mexe em roteiro,
    narração nem nas outras cenas."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)

    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    titulo = metadados.get("titulo", slug)

    _marcar_imagem_base_da_cena(caminho_meta, indice, None)
    # descrição que você escreveu pra essa imagem (vazia = volta a usar o texto da cena)
    # (descricao None = o campo nem foi aberto: mantém o que já estava valendo)
    if descricao is not None:
        with _trava_metadados_cenas:
            meta = json.loads(caminho_meta.read_text(encoding="utf-8"))
            mapa = meta.get("descricoes_cenas") or {}
            if descricao.strip():
                mapa[str(indice)] = descricao.strip()[:300]
            else:
                mapa.pop(str(indice), None)
            meta["descricoes_cenas"] = mapa
            caminho_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    job = jobs.criar_job_cena(titulo, slug, indice)
    return {"job_id": job.id}


_trava_metadados_cenas = threading.Lock()


def _marcar_imagem_base_da_cena(caminho_meta: Path, indice: int, nome: str | None, video: str | None = None) -> None:
    """Registra (ou limpa, com None) qual imagem da Base está numa cena — é o que faz a Base mostrar "usado em"."""
    with _trava_metadados_cenas:
        meta = json.loads(caminho_meta.read_text(encoding="utf-8"))
        mapa = meta.get("imagens_base_cenas") or {}
        mapa_videos = meta.get("videos_base_cenas") or {}
        mapa.pop(str(indice), None)
        mapa_videos.pop(str(indice), None)  # a cena é imagem OU vídeo, nunca os dois
        if nome:
            mapa[str(indice)] = nome
        if video:
            mapa_videos[str(indice)] = video
        meta["imagens_base_cenas"] = mapa
        meta["videos_base_cenas"] = mapa_videos
        caminho_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


@app.post("/api/videos/{slug}/cenas/estrutura")
def api_estrutura_das_cenas(
    slug: str, operacao: str = Form(...), indice: int | None = Form(None), posicao: int | None = Form(None),
    texto: str = Form(""), descricao_imagem: str = Form(""), midia_tipo: str = Form(""), midia_nome: str = Form(""),
    edicoes: str = Form(""),
) -> dict:
    """Adiciona uma cena (narração nova + imagem/vídeo), remove uma ou troca o texto de várias — sem regenerar
    o vídeo inteiro. Roda como job (leva um tempo)."""
    caminho_meta = RAIZ_SAIDA / slug / "metadata.json"
    if "/" in slug or "\\" in slug or not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)
    if operacao not in ("adicionar", "remover", "substituir"):
        return JSONResponse({"erro": "operação inválida"}, status_code=400)
    try:
        mapa_edicoes = json.loads(edicoes) if edicoes else None
    except ValueError:
        return JSONResponse({"erro": "edições inválidas"}, status_code=400)
    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    if metadados.get("publicado"):
        return JSONResponse({"erro": "esse vídeo já foi publicado"}, status_code=409)
    if operacao == "remover" and len(metadados.get("cenas") or []) < 2:
        return JSONResponse({"erro": "o vídeo precisa de pelo menos uma cena"}, status_code=400)
    job = jobs.criar_job_funcao(
        metadados.get("titulo", slug),
        lambda cb: _resultado_videos(slug, pipeline_mod.editar_estrutura(
            slug, operacao, indice, posicao, texto, descricao_imagem, midia_tipo, midia_nome, mapa_edicoes, progresso=cb)),
        estimativa=90.0 if operacao == "adicionar" else 60.0,
    )
    return {"job_id": job.id}


@app.get("/api/cenas-padrao")
def api_listar_cenas_padrao(canal: str = "") -> dict:
    return {"cenas": [c for c in biblioteca.listar_cenas_padrao() if not canal or c.get("canal_id", "") in ("", canal)]}


@app.post("/api/cenas-padrao")
def api_salvar_cena_padrao(
    id: str = Form(""), nome: str = Form(""), texto: str = Form(""), midia_tipo: str = Form(""), midia_nome: str = Form(""),
    posicao_padrao: str = Form("fim"),
) -> JSONResponse:
    try:
        return JSONResponse(biblioteca.salvar_cena_padrao(id or None, nome, texto, midia_tipo, midia_nome, canais_mod.canal_ativo_id(), posicao_padrao))
    except ValueError as erro:
        return JSONResponse({"erro": str(erro)}, status_code=400)


@app.delete("/api/cenas-padrao/{id}")
def api_remover_cena_padrao(id: str) -> JSONResponse:
    if not biblioteca.remover_cena_padrao(id):
        return JSONResponse({"erro": "cena padrão não encontrada"}, status_code=404)
    return JSONResponse({"ok": True})


@app.post("/api/videos/{slug}/cenas/duracoes")
def api_duracoes_das_cenas(slug: str, duracoes: str = Form(...)) -> dict:
    """Novo tempo de cada cena ({"indice": segundos}). Só aumenta: as cenas seguintes são empurradas pra frente."""
    caminho_meta = RAIZ_SAIDA / slug / "metadata.json"
    if "/" in slug or "\\" in slug or not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)
    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    if metadados.get("publicado"):
        return JSONResponse({"erro": "esse vídeo já foi publicado"}, status_code=409)
    try:
        pedido = {str(int(k)): float(v) for k, v in json.loads(duracoes).items()}
    except (ValueError, AttributeError, TypeError):
        return JSONResponse({"erro": "tempos inválidos"}, status_code=400)
    job = jobs.criar_job_funcao(metadados.get("titulo", slug), lambda cb: _resultado_videos(slug, pipeline_mod.aplicar_duracoes(slug, pedido, progresso=cb)), estimativa=60.0)
    return {"job_id": job.id}


@app.post("/api/videos/{slug}/cenas/{indice}/imagem-base")
def api_imagem_da_base_na_cena(slug: str, indice: int, nome: str = Form(...)) -> dict:
    """Coloca uma imagem da Base numa cena (recortada pros dois formatos) e remonta o vídeo."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)
    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    if not (0 <= indice < len(metadados.get("cenas") or [])):
        return JSONResponse({"erro": "cena não existe"}, status_code=404)
    origem = biblioteca.caminho_imagem_valida(nome)
    if origem is None:
        return JSONResponse({"erro": "imagem da Base inválida"}, status_code=400)
    temporaria = pasta / f"cena{indice:02d}_upload.png"
    Image.open(origem).convert("RGB").save(temporaria, "PNG")
    _marcar_imagem_base_da_cena(caminho_meta, indice, origem.name)
    job = jobs.criar_job_cena(metadados.get("titulo", slug), slug, indice, imagem_propria=temporaria)
    return {"job_id": job.id}


@app.post("/api/videos/{slug}/cenas/{indice}/imagem")
async def api_enviar_imagem_cena(slug: str, indice: int, arquivo: UploadFile = File(...)) -> dict:
    """Troca a imagem de uma cena por uma sua (recortada pros dois formatos) e
    remonta o vídeo — sem chamar a IA."""
    pasta = RAIZ_SAIDA / slug
    caminho_meta = pasta / "metadata.json"
    if not caminho_meta.exists():
        return JSONResponse({"erro": "vídeo não encontrado"}, status_code=404)
    metadados = json.loads(caminho_meta.read_text(encoding="utf-8"))
    cenas = metadados.get("cenas") or []
    if not (0 <= indice < len(cenas)):
        return JSONResponse({"erro": "cena não existe"}, status_code=404)

    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAX_UPLOAD_BYTES:
        return JSONResponse({"erro": "arquivo maior que 20MB"}, status_code=400)
    try:
        imagem = Image.open(io.BytesIO(conteudo))
        imagem.load()
        imagem = imagem.convert("RGB")
    except Exception:
        return JSONResponse({"erro": "não consegui abrir esse arquivo como imagem"}, status_code=400)

    temporaria = pasta / f"cena{indice:02d}_upload.png"
    imagem.save(temporaria, "PNG")
    _marcar_imagem_base_da_cena(caminho_meta, indice, None)
    job = jobs.criar_job_cena(metadados.get("titulo", slug), slug, indice, imagem_propria=temporaria)
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def api_status_job(job_id: str) -> JSONResponse:
    job = jobs.obter_job(job_id)
    if job is None:
        return JSONResponse({"erro": "job não encontrado"}, status_code=404)
    if job.status == "aguardando":
        job.etapa = f"Na fila — {jobs.posicao_na_fila(job)}º a ser gerado"
    return JSONResponse(
        {
            "status": job.status,
            "etapa": job.etapa,
            "progresso": job.progresso,
            "restante_segundos": jobs.tempo_ate_terminar(job) if job.status in ("rodando", "aguardando") else 0,
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
        if not (v16.exists() or v9.exists()):
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
                "hora_postagem": metadados.get("hora_postagem"),
                "duracao_segundos": metadados.get("duracao_segundos"),
                "status": _status_de(metadados),
                "video_16_9": f"/videos/{pasta.name}/video_16x9.mp4?v={int(v16.stat().st_mtime)}" if v16.exists() else None,
                "video_9_16": f"/videos/{pasta.name}/video_9x16.mp4?v={int(v9.stat().st_mtime)}" if v9.exists() else None,
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
                "thumbnail_tamanho_px": _tamanho_fonte_de(metadados),
                "thumbnail_pos_x": metadados.get("thumbnail_pos_x"),
                "thumbnail_pos_y": metadados.get("thumbnail_pos_y"),
                "thumbnail_base": _thumbnail_base_url(pasta),
                "thumbnail_efeito": metadados.get("thumbnail_efeito", "nenhum"),
                "aprovado": bool(metadados.get("aprovado", False)),
                "editado": bool(metadados.get("editado", False)),
                "transicao": metadados.get("transicao", "fade"),
                "legenda": subtitles_mod.normalizar_config(metadados.get("legenda")),
                "tem_cues": (pasta / "cues.json").exists(),
                "thumbnail_short": thumbnail_mod.config_shorts(metadados, pasta.name) if (pasta / "video_9x16.mp4").exists() or metadados.get("formatos") != "normal" else None,
                "thumbnail_short_url": f"/videos/{pasta.name}/thumbnail_shorts.png?v={int((pasta / 'thumbnail_shorts.png').stat().st_mtime)}" if (pasta / "thumbnail_shorts.png").exists() else None,
                "thumbnail_short_fundo_url": f"/videos/{pasta.name}/thumbnail_shorts_fundo.png" if (pasta / "thumbnail_shorts_fundo.png").exists() else None,
            }
        )

    # vídeos novos ainda sendo gerados (sem pasta/mp4 ainda) — mostra na Fila
    # como "processando" em vez de simplesmente não aparecer até terminar.
    # Regenerar/cena não entra aqui: a pasta e os mp4 antigos já existem, então
    # já aparecem no loop acima com o status de sempre até o novo mp4 sobrescrever.
    # vídeo já existente que está sendo (re)gerado agora: aparece como "processando", com progresso e tempo restante
    ativos = {slug_titulo(j.titulo): j for j in jobs.listar_rodando() if j.na_fila}
    for v in videos:
        j = ativos.get(v["slug"])
        if j:
            v.update(
                status="processando",
                job_etapa=f"Na fila — {jobs.posicao_na_fila(j)}º" if j.status == "aguardando" else j.etapa,
                job_progresso=j.progresso,
                job_restante_segundos=jobs.tempo_ate_terminar(j),
            )
    slugs_existentes = {v["slug"] for v in videos}
    for job in jobs.listar_rodando():
        slug_job = slug_titulo(job.titulo)
        if slug_job in slugs_existentes:
            continue
        slugs_existentes.add(slug_job)
        canal_info = canal.obter_canal(job.canal_id or canal.CANAL_PADRAO_ID)
        videos.insert(
            0,
            {
                "slug": slug_job,
                "titulo": job.titulo,
                "canal_id": job.canal_id or canal.CANAL_PADRAO_ID,
                "canal_nome": canal_info["nome"] if canal_info else (job.canal_id or canal.CANAL_PADRAO_ID),
                "sem_narracao": False,
                "som_fundo_tipo": "",
                "data_postagem": None,
                "hora_postagem": None,
                "duracao_segundos": None,
                "status": "processando",
                "job_etapa": f"Na fila — {jobs.posicao_na_fila(job)}º" if job.status == "aguardando" else job.etapa,
                "job_progresso": job.progresso,
                "job_restante_segundos": jobs.tempo_ate_terminar(job),
                "video_16_9": None,
                "video_9_16": None,
                "thumbnail": None,
                "modificado_em": time.time(),
                "tags": "",
                "publicado": False,
                "youtube_video_id": None,
                "publicacao_erro": None,
                "tem_cenas": False,
                "thumbnail_texto": job.titulo,
                "thumbnail_cor": "",
                "thumbnail_posicao": "baixo-centro",
                "thumbnail_tamanho_px": 80,
                "thumbnail_pos_x": None,
                "thumbnail_pos_y": None,
                "thumbnail_base": None,
            },
        )
    return videos
