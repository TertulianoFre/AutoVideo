"""Texto por IA com vários provedores em cadeia. Quem tem chave (ou o Ollama local) é usado primeiro, em rodízio
pra dividir a carga; a Pollinations (sem chave, mas com limite de 1 pedido por vez) fica de reserva.
Se um provedor estoura o limite (429) ou cai, ele descansa um tempo e o próximo assume — assim gerar dezenas
de roteiros por dia não trava num serviço só.

As chaves ficam no .env (já ignorado pelo git) ou em variáveis de ambiente."""

import os
import re
import threading
import time
from pathlib import Path

import requests

ENV = Path(__file__).resolve().parent.parent / ".env"

# nome -> (url, modelo padrão, variável da chave, onde criar a chave grátis)
PROVEDORES = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b", "GROQ_API_KEY", "console.groq.com"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-flash-latest", "GEMINI_API_KEY", "aistudio.google.com/apikey"),
    "mistral": ("https://api.mistral.ai/v1/chat/completions", "mistral-small-latest", "MISTRAL_API_KEY", "console.mistral.ai"),
    "cerebras": ("https://api.cerebras.ai/v1/chat/completions", "gpt-oss-120b", "CEREBRAS_API_KEY", "cloud.cerebras.ai"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "google/gemma-4-31b-it:free", "OPENROUTER_API_KEY", "openrouter.ai/keys"),
}
OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
POLLINATIONS_URL = "https://text.pollinations.ai/openai"

_descanso: dict = {}  # provedor -> instante em que volta a ser usado
_trava = threading.Lock()
_rodizio = 0


def _ler_env(nome: str) -> str:
    valor = os.environ.get(nome, "").strip()
    if valor:
        return valor
    if ENV.exists():
        for linha in ENV.read_text(encoding="utf-8").splitlines():
            n, _, v = linha.partition("=")
            if n.strip() == nome:
                return v.strip().strip('"').strip("'")
    return ""


def gravar_chave(provedor: str, chave: str) -> None:
    """Guarda (ou apaga, se vazia) a chave do provedor no .env."""
    if provedor not in PROVEDORES:
        raise ValueError("Provedor desconhecido.")
    nome = PROVEDORES[provedor][2]
    linhas = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    linhas = [l for l in linhas if l.partition("=")[0].strip() != nome]
    chave = re.sub(r"\s+", "", chave or "")
    if chave:
        linhas.append(f"{nome}={chave}")
    ENV.write_text("\n".join(linhas) + ("\n" if linhas else ""), encoding="utf-8")
    _descanso.pop(provedor, None)


def _ollama_ativo() -> bool:
    if _ler_env("OLLAMA_MODEL"):
        return True
    try:
        return requests.get("http://localhost:11434/api/tags", timeout=0.4).ok
    except requests.RequestException:
        return False


def status() -> list:
    agora = time.time()
    saida = []
    for nome, (_, modelo, var, site) in PROVEDORES.items():
        saida.append({"id": nome, "chave": bool(_ler_env(var)), "modelo": _ler_env(f"{nome.upper()}_MODEL") or modelo, "site": site,
                      "descansando": max(0, int(_descanso.get(nome, 0) - agora))})
    saida.append({"id": "ollama", "chave": _ollama_ativo(), "modelo": _ler_env("OLLAMA_MODEL") or "(o primeiro modelo instalado)", "site": "ollama.com (roda no seu PC, sem limite)", "descansando": max(0, int(_descanso.get("ollama", 0) - agora))})
    saida.append({"id": "pollinations", "chave": True, "modelo": "openai", "site": "sem chave (limite de 1 pedido por vez)", "descansando": max(0, int(_descanso.get("pollinations", 0) - agora))})
    return saida


def _texto_da_resposta(resposta) -> str:
    dados = resposta.json()
    escolhas = dados.get("choices") or []
    texto = escolhas[0].get("message", {}).get("content", "") if escolhas else ""
    return re.sub(r"<\|[^|>]*\|>", "", texto or "").strip()


def _chamar_openai_compat(url: str, modelo: str, chave: str, mensagens: list, extra: dict | None = None, tempo: int = 60) -> str:
    cab = {"Authorization": f"Bearer {chave}"} if chave else {}
    corpo = {"model": modelo, "messages": mensagens, **(extra or {})}
    resposta = requests.post(url, json=corpo, headers=cab, timeout=tempo)
    if resposta.status_code == 429:
        raise LimiteAtingido(resposta.headers.get("retry-after", ""))
    if not resposta.ok:
        raise RuntimeError(f"HTTP {resposta.status_code}: {resposta.text[:160]}")
    texto = _texto_da_resposta(resposta)
    if not texto:
        raise RuntimeError("resposta sem conteúdo")
    return texto


class LimiteAtingido(Exception):
    pass


def _modelo_ollama() -> str:
    modelo = _ler_env("OLLAMA_MODEL")
    if modelo:
        return modelo
    dados = requests.get("http://localhost:11434/api/tags", timeout=2).json()
    modelos = dados.get("models") or []
    if not modelos:
        raise RuntimeError("Ollama sem modelos instalados")
    return modelos[0]["name"]


def _candidatos() -> list:
    """Provedores com chave em rodízio (divide a carga), depois Ollama, depois Pollinations. Os que estão
    descansando (estouraram o limite há pouco) vão pro fim."""
    global _rodizio
    agora = time.time()
    com_chave = [n for n, (_, _, var, _) in PROVEDORES.items() if _ler_env(var)]
    with _trava:
        if com_chave:
            _rodizio = (_rodizio + 1) % len(com_chave)
            com_chave = com_chave[_rodizio:] + com_chave[:_rodizio]
    ordem = com_chave + (["ollama"] if _ollama_ativo() else []) + ["pollinations"]
    livres = [n for n in ordem if _descanso.get(n, 0) <= agora]
    return livres + [n for n in ordem if n not in livres]


def chamar_ia(mensagens: list, tentativas: int = 4) -> str:
    """Tenta cada provedor disponível; a Pollinations (sem chave) recebe as tentativas com espera."""
    erros = []
    for nome in _candidatos():
        try:
            if nome == "pollinations":
                return _pollinations(mensagens, tentativas)
            if nome == "ollama":
                return _chamar_openai_compat(OLLAMA_URL, _modelo_ollama(), "", mensagens, tempo=300)
            url, modelo, var, _ = PROVEDORES[nome]
            return _chamar_openai_compat(url, _ler_env(f"{nome.upper()}_MODEL") or modelo, _ler_env(var), mensagens)
        except LimiteAtingido as e:
            espera = int(e.args[0]) if e.args and str(e.args[0]).isdigit() else 60
            _descanso[nome] = time.time() + min(max(espera, 20), 300)
            erros.append(f"{nome}: limite atingido")
        except (requests.RequestException, RuntimeError, ValueError) as e:
            sem_acesso = str(e).startswith(("HTTP 401", "HTTP 402", "HTTP 403"))  # chave sem permissão/crédito: não insiste toda hora
            _descanso[nome] = time.time() + (3600 if sem_acesso else 30)
            erros.append(f"{nome}: {str(e)[:120]}")
    raise RuntimeError("Nenhum provedor de IA respondeu (" + "; ".join(erros) + ")")


def _pollinations(mensagens: list, tentativas: int) -> str:
    # reasoning_effort baixo: esse modelo às vezes gasta todo o orçamento de tokens "pensando"
    ultimo = None
    for tentativa in range(1, tentativas + 1):
        try:
            return _chamar_openai_compat(POLLINATIONS_URL, "openai", "", mensagens, {"reasoning_effort": "low"})
        except LimiteAtingido:
            ultimo = "429"
        except (requests.RequestException, RuntimeError, ValueError) as e:
            ultimo = str(e)
        time.sleep(2 * tentativa)
    raise RuntimeError(f"Pollinations falhou {tentativas}x ({ultimo})")


# ---------------------------------------------------------------------------
# visão: descrever uma imagem (só provedores que enxergam; a Pollinations não)
# ---------------------------------------------------------------------------

MODELOS_VISAO = {
    "gemini": "gemini-flash-latest",
    "mistral": "mistral-small-latest",
    "groq": "qwen/qwen3.8-27b",
    "openrouter": "google/gemma-4-31b-it:free",
}

PEDIDO_DESCRICAO = (
    "Descreva em UMA frase curta em português do Brasil (até 25 palavras) o que aparece nesta imagem: "
    "o assunto principal, o que está acontecendo e o cenário. Só fatos visíveis, sem opinião, sem começar com 'A imagem'."
)


def visao_disponivel() -> bool:
    return any(_ler_env(PROVEDORES[n][2]) for n in MODELOS_VISAO) or bool(_ler_env("OLLAMA_VISION_MODEL"))


def descrever_imagem(caminho_png_ou_jpg: Path) -> str:
    import base64

    dados = base64.b64encode(Path(caminho_png_ou_jpg).read_bytes()).decode()
    sufixo = "jpeg" if str(caminho_png_ou_jpg).lower().endswith((".jpg", ".jpeg")) else "png"
    conteudo = [{"type": "text", "text": PEDIDO_DESCRICAO}, {"type": "image_url", "image_url": {"url": f"data:image/{sufixo};base64,{dados}"}}]
    mensagens = [{"role": "user", "content": conteudo}]
    erros = []
    for nome in [n for n in MODELOS_VISAO if _ler_env(PROVEDORES[n][2])]:
        if _descanso.get(nome, 0) > time.time():
            continue
        try:
            url, _, var, _ = PROVEDORES[nome]
            texto = _chamar_openai_compat(url, _ler_env(f"{nome.upper()}_VISION_MODEL") or MODELOS_VISAO[nome], _ler_env(var), mensagens, tempo=45)
            return texto.strip().strip('"')[:300]
        except LimiteAtingido:
            _descanso[nome] = time.time() + 60
            erros.append(f"{nome}: limite")
        except (requests.RequestException, RuntimeError, ValueError) as e:
            erros.append(f"{nome}: {str(e)[:100]}")
    modelo = _ler_env("OLLAMA_VISION_MODEL")
    if modelo:
        try:
            return _chamar_openai_compat(OLLAMA_URL, modelo, "", mensagens, tempo=180).strip()[:300]
        except (requests.RequestException, RuntimeError, ValueError) as e:
            erros.append(f"ollama: {str(e)[:100]}")
    raise RuntimeError("Nenhum provedor com visão respondeu. " + ("; ".join(erros) or "Coloque uma chave grátis do Gemini ou Groq."))
