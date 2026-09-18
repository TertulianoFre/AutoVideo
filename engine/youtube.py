"""Login e publicação no YouTube via YouTube Data API v3.

Autorização é feita uma vez por conta (abre o navegador, você loga e
autoriza); depois fica salva localmente em dados/tokens/ e só pede de novo se
expirar (contas em modo "teste" no Google expiram a cada 7 dias — limitação
do Google, não do código)."""

import re
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

RAIZ = Path(__file__).resolve().parent.parent
CLIENT_SECRET_PATH = RAIZ / "client_secret.json"
PASTA_TOKENS = RAIZ / "dados" / "tokens"

ESCOPOS = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",  # pro painel: inscritos, visualizações
    "https://www.googleapis.com/auth/yt-analytics.readonly",  # pro painel: gráficos por dia (YouTube Analytics API)
]
CATEGORIA_PADRAO = "22"  # "Pessoas e blogs" — genérica, serve pra a maioria dos vídeos do canal


def _caminho_token(nome_conta: str) -> Path:
    PASTA_TOKENS.mkdir(parents=True, exist_ok=True)
    return PASTA_TOKENS / f"token_{nome_conta}.json"


def contas_conectadas() -> list:
    if not PASTA_TOKENS.exists():
        return []
    return [p.stem.removeprefix("token_") for p in PASTA_TOKENS.glob("token_*.json")]


def _carregar_credenciais(nome_conta: str) -> Credentials | None:
    caminho = _caminho_token(nome_conta)
    if not caminho.exists():
        return None
    try:
        # sem passar ESCOPOS aqui de propósito: usa os escopos que o token já
        # tem de verdade (gravados no próprio arquivo). Se pedir pra renovar
        # com um escopo diferente do que foi concedido originalmente (ex:
        # ESCOPOS cresceu desde que essa conta conectou), o Google rejeita o
        # refresh inteiro — a conta parece "desconectada" do nada.
        creds = Credentials.from_authorized_user_file(str(caminho))
    except (ValueError, OSError):
        return None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            caminho.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            return None
    return creds if creds and creds.valid else None


def esta_conectado(nome_conta: str) -> bool:
    return _carregar_credenciais(nome_conta) is not None


def conectar(nome_conta: str) -> None:
    """Abre o navegador pra autorizar essa conta. Bloqueia até você terminar
    o login — sempre chamar isso numa thread separada, nunca na thread
    principal do servidor."""
    if not CLIENT_SECRET_PATH.exists():
        raise RuntimeError(
            "client_secret.json não encontrado na raiz do projeto. "
            "Baixe as credenciais no Google Cloud Console primeiro."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), ESCOPOS)
    creds = flow.run_local_server(port=0, prompt="consent")
    _caminho_token(nome_conta).write_text(creds.to_json(), encoding="utf-8")


def obter_estatisticas_canal(nome_conta: str) -> dict:
    """Inscritos, visualizações totais e nº de vídeos do canal conectado.
    Precisa do escopo youtube.readonly — se a conta foi conectada antes desse
    escopo existir, vai faltar permissão até reconectar."""
    creds = _carregar_credenciais(nome_conta)
    if creds is None:
        raise RuntimeError(f"Conta '{nome_conta}' não está conectada ao YouTube.")

    youtube = build("youtube", "v3", credentials=creds)
    resposta = youtube.channels().list(part="statistics,snippet", mine=True).execute()
    itens = resposta.get("items") or []
    if not itens:
        raise RuntimeError("Nenhum canal encontrado pra essa conta.")

    canal = itens[0]
    snippet = canal.get("snippet", {})
    estatisticas = canal.get("statistics", {})
    channel_id = canal.get("id", "")
    custom_url = snippet.get("customUrl")  # ex: "@meucanal", já vem com @ quando existe
    miniaturas = snippet.get("thumbnails", {})
    avatar = (miniaturas.get("default") or miniaturas.get("medium") or {}).get("url")

    return {
        "nome_canal": snippet.get("title", ""),
        "avatar_url": avatar,
        "canal_url": f"https://www.youtube.com/{custom_url}" if custom_url else f"https://www.youtube.com/channel/{channel_id}",
        "inscritos": int(estatisticas.get("subscriberCount", 0)),
        "visualizacoes": int(estatisticas.get("viewCount", 0)),
        "total_videos": int(estatisticas.get("videoCount", 0)),
    }


def obter_serie_diaria(nome_conta: str, dias: int = 28) -> list:
    """Views e inscritos (ganhos - perdidos) por dia, dos últimos `dias` dias.
    Usa a YouTube Analytics API: precisa dela ativada no Google Cloud e do
    escopo yt-analytics.readonly (contas conectadas antes precisam reconectar)."""
    from datetime import date, timedelta

    creds = _carregar_credenciais(nome_conta)
    if creds is None:
        raise RuntimeError(f"Conta '{nome_conta}' não está conectada ao YouTube.")

    analytics = build("youtubeAnalytics", "v2", credentials=creds)
    fim = date.today()
    inicio = fim - timedelta(days=dias - 1)
    resposta = analytics.reports().query(
        ids="channel==MINE",
        startDate=inicio.isoformat(),
        endDate=fim.isoformat(),
        metrics="views,subscribersGained,subscribersLost",
        dimensions="day",
        sort="day",
    ).execute()

    por_dia = {linha[0]: linha for linha in resposta.get("rows", [])}
    serie = []
    for i in range(dias):
        dia = (inicio + timedelta(days=i)).isoformat()
        linha = por_dia.get(dia)
        serie.append(
            {
                "dia": dia,
                "views": int(linha[1]) if linha else 0,
                "inscritos_liquidos": int(linha[2]) - int(linha[3]) if linha else 0,
            }
        )
    return serie


def obter_tendencias(nome_conta: str, regiao: str = "BR", quantidade: int = 15) -> list:
    """Títulos dos vídeos em alta no YouTube agora — usado como inspiração pro
    Agente sugerir ideias (não copia os títulos, só usa como contexto do que
    está bombando)."""
    creds = _carregar_credenciais(nome_conta)
    if creds is None:
        raise RuntimeError(f"Conta '{nome_conta}' não está conectada ao YouTube.")

    youtube = build("youtube", "v3", credentials=creds)
    resposta = youtube.videos().list(part="snippet", chart="mostPopular", regionCode=regiao, maxResults=quantidade).execute()
    return [item["snippet"]["title"] for item in resposta.get("items", []) if item.get("snippet")]


def _tags_validas(tags: list) -> list:
    """O YouTube recusa o upload inteiro se uma tag tiver caracteres inválidos
    (< > etc.) ou o total passar de 500 caracteres — limpa antes de enviar."""
    limpas, total = [], 0
    for tag in tags:
        tag = re.sub(r"<\|[^|>]*\|>", "", tag)
        tag = re.sub(r"[<>|#]", "", tag).strip()[:60]
        if not tag or tag.casefold() in (t.casefold() for t in limpas):
            continue
        if total + len(tag) + 1 > 480:
            break
        limpas.append(tag)
        total += len(tag) + 1
    return limpas


def definir_thumbnail(nome_conta: str, video_id: str, caminho_imagem: Path) -> None:
    """Envia a thumbnail personalizada. O upload do vídeo não leva ela junto —
    é uma chamada separada. Precisa que o canal esteja verificado (telefone) no
    YouTube pra permitir thumbnails personalizadas."""
    creds = _carregar_credenciais(nome_conta)
    if creds is None:
        raise RuntimeError(f"Conta '{nome_conta}' não está conectada ao YouTube.")
    youtube = build("youtube", "v3", credentials=creds)
    youtube.thumbnails().set(
        videoId=video_id, media_body=MediaFileUpload(str(caminho_imagem), mimetype="image/png")
    ).execute()


def publicar_video(
    caminho_video: Path,
    titulo: str,
    descricao: str,
    tags: list,
    nome_conta: str,
    privacidade: str = "private",
    is_short: bool = False,
) -> str:
    """Publica o vídeo no canal da conta conectada, devolve o ID no YouTube.
    privacidade: "private" | "unlisted" | "public" — comece com "private" ou
    "unlisted" até confiar no fluxo automático."""
    creds = _carregar_credenciais(nome_conta)
    if creds is None:
        raise RuntimeError(f"Conta '{nome_conta}' não está conectada ao YouTube.")

    youtube = build("youtube", "v3", credentials=creds)

    tags = _tags_validas(tags)
    titulo_final = f"{titulo} #Shorts" if is_short else titulo
    corpo = {
        "snippet": {
            "title": titulo_final[:100],
            "description": descricao[:5000],
            "tags": tags[:500],
            "categoryId": CATEGORIA_PADRAO,
        },
        "status": {"privacyStatus": privacidade, "selfDeclaredMadeForKids": False},
    }

    midia = MediaFileUpload(str(caminho_video), mimetype="video/mp4", resumable=True)
    solicitacao = youtube.videos().insert(part="snippet,status", body=corpo, media_body=midia)

    resposta = None
    while resposta is None:
        _progresso, resposta = solicitacao.next_chunk()
    return resposta["id"]
