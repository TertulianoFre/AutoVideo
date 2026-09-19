"""Biblioteca local de mídia reutilizável entre vídeos: áudios (música/efeitos
livres de direito que você mesmo importa) e imagens (pra usar de base em
thumbnails, por exemplo). Fica salvo em dados/biblioteca/, fora da pasta de
qualquer vídeo específico, pra poder ser usada em qualquer vídeo novo."""

import io
import json
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from engine.ferramentas import caminho_ffmpeg

RAIZ = Path(__file__).resolve().parent.parent / "dados" / "biblioteca"
PASTA_AUDIOS = RAIZ / "audios"
PASTA_IMAGENS = RAIZ / "imagens"
PASTA_VIDEOS = RAIZ / "videos"
TAMANHO_MAX_VIDEO_BYTES = 250 * 1024 * 1024

TAMANHO_MAX_BYTES = 40 * 1024 * 1024


def _garantir_pastas() -> None:
    PASTA_AUDIOS.mkdir(parents=True, exist_ok=True)
    PASTA_IMAGENS.mkdir(parents=True, exist_ok=True)
    PASTA_VIDEOS.mkdir(parents=True, exist_ok=True)


def _slug_arquivo(nome: str) -> str:
    base = Path(nome).stem.strip().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base)
    return base.strip("-")[:50]


def _nome_unico(pasta: Path, base: str, extensao: str) -> Path:
    candidato = pasta / f"{base}{extensao}"
    i = 2
    while candidato.exists():
        candidato = pasta / f"{base}-{i}{extensao}"
        i += 1
    return candidato


def listar_audios() -> list[str]:
    _garantir_pastas()
    return sorted(p.name for p in PASTA_AUDIOS.iterdir() if p.is_file())


def listar_imagens() -> list[str]:
    _garantir_pastas()
    return sorted(p.name for p in PASTA_IMAGENS.iterdir() if p.is_file())


def listar_videos() -> list[str]:
    _garantir_pastas()
    return sorted(p.name for p in PASTA_VIDEOS.iterdir() if p.is_file())


def salvar_video(nome_sugerido: str, conteudo: bytes) -> str:
    """Reencoda pra mp4 (H.264, no máximo 1080p, 30 fps) antes de guardar — assim qualquer
    formato de entrada (mov, webm, mkv...) vira algo que o ffmpeg do app sempre consegue usar,
    e arquivo que não é vídeo de verdade é rejeitado. O áudio, se existir, é mantido."""
    _garantir_pastas()
    if len(conteudo) > TAMANHO_MAX_VIDEO_BYTES:
        raise ValueError("arquivo grande demais (máximo 250 MB)")
    destino = _nome_unico(PASTA_VIDEOS, _slug_arquivo(nome_sugerido) or "video", ".mp4")
    with tempfile.NamedTemporaryFile(suffix=Path(nome_sugerido).suffix or ".bin", delete=False) as tmp:
        tmp.write(conteudo)
        caminho_tmp = Path(tmp.name)
    try:
        comando = [
            caminho_ffmpeg(), "-y", "-i", str(caminho_tmp),
            "-vf", "scale='min(1920,iw)':-2,fps=30,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(destino),
        ]
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.returncode != 0 or not destino.exists():
            destino.unlink(missing_ok=True)
            raise ValueError("não consegui reconhecer esse arquivo como vídeo válido")
    finally:
        caminho_tmp.unlink(missing_ok=True)
    return destino.name


def remover_video(nome: str) -> bool:
    return _remover(PASTA_VIDEOS, nome)


def caminho_video_valido(nome: str) -> Path | None:
    return PASTA_VIDEOS / nome if nome in listar_videos() else None


def salvar_audio(nome_sugerido: str, conteudo: bytes) -> str:
    """Reencoda com ffmpeg antes de salvar — se o arquivo não for áudio de
    verdade, o ffmpeg falha e a gente rejeita, em vez de guardar bytes crus
    não confiáveis. Sempre normaliza pra .mp3, nome único pra não sobrescrever."""
    _garantir_pastas()
    if len(conteudo) > TAMANHO_MAX_BYTES:
        raise ValueError("arquivo grande demais (máximo 40 MB)")

    nome_base = _slug_arquivo(nome_sugerido) or "audio"
    destino = _nome_unico(PASTA_AUDIOS, nome_base, ".mp3")

    with tempfile.NamedTemporaryFile(suffix=Path(nome_sugerido).suffix or ".bin", delete=False) as tmp:
        tmp.write(conteudo)
        caminho_tmp = Path(tmp.name)
    try:
        comando = [caminho_ffmpeg(), "-y", "-i", str(caminho_tmp), "-vn", "-acodec", "libmp3lame", "-q:a", "3", str(destino)]
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.returncode != 0 or not destino.exists():
            destino.unlink(missing_ok=True)
            raise ValueError("não consegui reconhecer esse arquivo como áudio válido")
    finally:
        caminho_tmp.unlink(missing_ok=True)
    return destino.name


def salvar_imagem(nome_sugerido: str, conteudo: bytes) -> str:
    """Mesmo padrão usado pro upload de thumbnail: sempre redecodifica com o
    PIL (nunca confia nos bytes crus) e resalva como PNG."""
    _garantir_pastas()
    if len(conteudo) > TAMANHO_MAX_BYTES:
        raise ValueError("arquivo grande demais (máximo 40 MB)")

    imagem = Image.open(io.BytesIO(conteudo))
    imagem.load()
    imagem = imagem.convert("RGB")

    nome_base = _slug_arquivo(nome_sugerido) or "imagem"
    destino = _nome_unico(PASTA_IMAGENS, nome_base, ".png")
    imagem.save(destino, "PNG")
    return destino.name


def remover_audio(nome: str) -> bool:
    return _remover(PASTA_AUDIOS, nome)


def remover_imagem(nome: str) -> bool:
    return _remover(PASTA_IMAGENS, nome)


def _remover(pasta: Path, nome: str) -> bool:
    nomes_validos = {p.name for p in pasta.glob("*") if p.is_file()}
    if nome not in nomes_validos:
        return False
    (pasta / nome).unlink()
    return True


def caminho_audio_valido(nome: str) -> Path | None:
    """Só retorna um Path se `nome` bater com um arquivo que realmente existe
    na biblioteca — defesa contra path traversal vindo de um nome arbitrário
    do cliente (nunca junta o nome cru num Path sem checar antes)."""
    return PASTA_AUDIOS / nome if nome in listar_audios() else None


def caminho_imagem_valida(nome: str) -> Path | None:
    return PASTA_IMAGENS / nome if nome in listar_imagens() else None


def preparar_audio_para_video(nome: str, duracao_segundos: float, destino: Path) -> Path:
    """Corta (ou repete em loop, se for mais curto) um áudio da biblioteca pra
    caber exatamente na duração pedida — usado tanto como som de fundo por
    baixo da narração quanto como o áudio inteiro (modo sem narração)."""
    origem = caminho_audio_valido(nome)
    if origem is None:
        raise ValueError(f"áudio \"{nome}\" não encontrado na biblioteca")

    comando = [
        caminho_ffmpeg(), "-y",
        "-stream_loop", "-1", "-i", str(origem),
        "-t", f"{max(duracao_segundos, 0.1):.3f}",
        "-ar", "44100", "-ac", "2",
        str(destino),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ao preparar áudio da biblioteca:\n{resultado.stderr[-2000:]}")
    return destino


# ---------------------------------------------------------------------------
# cenas padrão: cenas prontas (narração + imagem/vídeo opcional) pra encaixar em qualquer vídeo
# (ex: "se inscreva no canal e deixe o seu like"). A narração é sintetizada com a voz do vídeo
# na hora de usar; a mídia vem da própria Base.
# ---------------------------------------------------------------------------

import json
import uuid

ARQUIVO_CENAS_PADRAO = RAIZ / "cenas_padrao.json"


def _imagem_inscreva_se() -> str:
    """Imagem inicial da cena "Inscreva-se": botão vermelho num fundo claro. Você pode trocar por um vídeo seu."""
    from PIL import ImageDraw, ImageFont

    _garantir_pastas()
    destino = PASTA_IMAGENS / "inscreva-se-padrao.png"
    if destino.exists():
        return destino.name
    largura, altura = 1920, 1080
    fundo = Image.new("RGB", (largura, altura), (238, 238, 240))
    d = ImageDraw.Draw(fundo)
    for y in range(altura):  # degradê suave, mais escuro nas bordas
        tom = int(236 - 26 * abs(y - altura / 2) / (altura / 2))
        d.line([(0, y), (largura, y)], fill=(tom, tom, tom + 2))
    fonte = None
    for caminho in ("C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        if Path(caminho).exists():
            fonte = ImageFont.truetype(caminho, 150)
            break
    fonte = fonte or ImageFont.load_default()
    x0, y0, x1, y1 = 330, 400, 1590, 640
    d.rounded_rectangle((x0 + 10, y0 + 16, x1 + 10, y1 + 16), radius=40, fill=(150, 150, 150))
    d.rounded_rectangle((x0, y0, x1, y1), radius=40, fill=(214, 20, 20))
    d.rounded_rectangle((x0 + 50, y0 + 60, x0 + 200, y0 + 180), radius=26, fill=(255, 255, 255))
    d.polygon([(x0 + 100, y0 + 85), (x0 + 100, y0 + 155), (x0 + 160, y0 + 120)], fill=(214, 20, 20))
    d.text((x0 + 250, y0 + 28), "INSCREVA-SE", font=fonte, fill=(255, 255, 255))
    pequena = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 74) if Path("C:/Windows/Fonts/arialbd.ttf").exists() else fonte
    d.text((largura // 2, 790), "e deixe o seu LIKE", font=pequena, fill=(60, 60, 60), anchor="mm")
    fundo.save(destino, "PNG")
    try:
        meta_arq = RAIZ / "meta.json"
        meta = json.loads(meta_arq.read_text(encoding="utf-8")) if meta_arq.exists() else {}
        meta.setdefault("imagens", {}).setdefault(destino.name, {"descricao": "Botão vermelho de INSCREVA-SE com convite para deixar o like", "canal_id": ""})
        meta_arq.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError):
        pass
    return destino.name


def _ler_cenas_padrao() -> list:
    try:
        return json.loads(ARQUIVO_CENAS_PADRAO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cenas_de_fabrica() -> list:
    return [
        {"id": "introducao", "nome": "Introdução (abertura)", "posicao_padrao": "inicio", "midia_tipo": "", "midia_nome": "",
         "texto": "Olá, tudo bem? Prepare-se, porque o vídeo de hoje vai te surpreender!"},
        {"id": "inscreva-se", "nome": "Inscreva-se e curta", "posicao_padrao": "fim", "midia_tipo": "imagem", "midia_nome": "",
         "texto": "Gostou do vídeo? Então se inscreva no canal e deixe o seu like!"},
    ]


def listar_cenas_padrao() -> list:
    """Lista as cenas padrão. As de fábrica (introdução e "inscreva-se") são criadas uma única vez: se você
    apagar uma, ela não volta."""
    _garantir_pastas()
    cenas = _ler_cenas_padrao() or []
    marcador = RAIZ / "cenas_padrao_criadas.json"
    try:
        criadas = json.loads(marcador.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        criadas = [c["id"] for c in cenas]  # instalação anterior: o que já existe conta como criado
    mudou = False
    for padrao in _cenas_de_fabrica():
        if padrao["id"] in criadas:
            continue
        if padrao["id"] == "inscreva-se":
            padrao["midia_nome"] = _imagem_inscreva_se()
        cenas.append(padrao)
        criadas.append(padrao["id"])
        mudou = True
    for c in cenas:  # cenas antigas ganham a posição padrão
        c.setdefault("posicao_padrao", "inicio" if c["id"] == "introducao" else "fim")
    if mudou or not ARQUIVO_CENAS_PADRAO.exists():
        _gravar_cenas_padrao(cenas)
        marcador.write_text(json.dumps(criadas), encoding="utf-8")
    return cenas


def _gravar_cenas_padrao(cenas: list) -> None:
    RAIZ.mkdir(parents=True, exist_ok=True)
    ARQUIVO_CENAS_PADRAO.write_text(json.dumps(cenas, ensure_ascii=False, indent=2), encoding="utf-8")


def salvar_cena_padrao(id_: str | None, nome: str, texto: str, midia_tipo: str, midia_nome: str, canal_id: str = "", posicao_padrao: str = "fim") -> dict:
    nome, texto = nome.strip()[:80], texto.strip()[:600]
    if not nome or len(texto) < 3:
        raise ValueError("dê um nome e o texto da narração dessa cena")
    if midia_tipo == "imagem" and caminho_imagem_valida(midia_nome) is None:
        raise ValueError("imagem não encontrada na Base")
    if midia_tipo == "video" and caminho_video_valido(midia_nome) is None:
        raise ValueError("vídeo não encontrado na Base")
    if midia_tipo not in ("imagem", "video"):
        midia_tipo, midia_nome = "", ""
    cenas = listar_cenas_padrao()
    item = next((c for c in cenas if c["id"] == id_), None) if id_ else None
    if item is None:
        item = {"id": uuid.uuid4().hex[:10], "canal_id": canal_id}  # nova: fica no canal ativo
        cenas.append(item)
    item.update(nome=nome, texto=texto, midia_tipo=midia_tipo, midia_nome=midia_nome, posicao_padrao="inicio" if posicao_padrao == "inicio" else "fim")
    _gravar_cenas_padrao(cenas)
    return item


def remover_cena_padrao(id_: str) -> bool:
    cenas = listar_cenas_padrao()
    restantes = [c for c in cenas if c["id"] != id_]
    if len(restantes) == len(cenas):
        return False
    _gravar_cenas_padrao(restantes)
    return True


_cache_duracao: dict = {}


def duracao_de(caminho: Path) -> float:
    """Duração (s) de um áudio/vídeo, com cache por data de modificação."""
    chave = (str(caminho), caminho.stat().st_mtime)
    if chave not in _cache_duracao:
        from engine.ferramentas import caminho_ffprobe
        r = subprocess.run([caminho_ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(caminho)], capture_output=True, text=True)
        try:
            _cache_duracao[chave] = round(float(r.stdout.strip()), 2)
        except ValueError:
            _cache_duracao[chave] = 0.0
    return _cache_duracao[chave]


def preparar_playlist_para_video(itens: list, duracao_segundos: float, destino: Path, repetir: bool = True, suave: bool = True, fade_final: bool = True) -> Path:
    """Monta o som de fundo com VÁRIOS áudios da Base, um depois do outro (com transição suave entre eles),
    cobrindo exatamente a duração do vídeo. `itens` = [{"nome": ..., "segundos": tempo máximo de cada áudio ou None}].
    Se a playlist for mais curta que o vídeo: repete (repetir=True) ou termina em silêncio. Se for mais longa, corta no fim."""
    faixas = []
    for item in itens:
        caminho = caminho_audio_valido(item.get("nome", ""))
        if caminho is None:
            raise ValueError(f'áudio "{item.get("nome")}" não encontrado na biblioteca')
        total = duracao_de(caminho)
        uso = min(total, float(item["segundos"])) if item.get("segundos") else total
        faixas.append((caminho, max(1.0, uso)))
    if not faixas:
        raise ValueError("nenhum áudio na playlist")

    cruzamento = 2.0 if suave else 0.0
    sequencia, coberto, i = [], 0.0, 0
    while True:
        caminho, uso = faixas[i % len(faixas)]
        sequencia.append((caminho, uso))
        coberto += uso - (cruzamento if len(sequencia) > 1 else 0)
        i += 1
        if coberto >= duracao_segundos or (not repetir and i >= len(faixas)) or len(sequencia) > 300:
            break
    cruz = min(cruzamento, min(u for _, u in sequencia) / 2) if len(sequencia) > 1 else 0.0

    entradas, filtros = [], []
    for k, (caminho, uso) in enumerate(sequencia):
        entradas += ["-t", f"{uso:.3f}", "-i", str(caminho)]
        filtros.append(f"[{k}:a]aresample=44100,aformat=channel_layouts=stereo[a{k}]")
    if len(sequencia) == 1:
        anterior = "[a0]"
    elif cruz > 0:
        anterior = "[a0]"
        for k in range(1, len(sequencia)):
            filtros.append(f"{anterior}[a{k}]acrossfade=d={cruz:.2f}[x{k}]")
            anterior = f"[x{k}]"
    else:
        filtros.append("".join(f"[a{k}]" for k in range(len(sequencia))) + f"concat=n={len(sequencia)}:v=0:a=1[cat]")
        anterior = "[cat]"
    final = f"{anterior}atrim=0:{duracao_segundos:.3f},asetpts=PTS-STARTPTS"
    if fade_final:
        final += f",afade=t=out:st={max(0.0, duracao_segundos - 3):.2f}:d=3"
    final += f",apad=whole_dur={duracao_segundos:.3f}[saida]"
    filtros.append(final)
    comando = [caminho_ffmpeg(), "-y", *entradas, "-filter_complex", ";".join(filtros), "-map", "[saida]", "-t", f"{duracao_segundos:.3f}", "-ar", "44100", "-ac", "2", str(destino)]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(f"FFmpeg falhou ao montar a playlist de áudio:\n{resultado.stderr[-1500:]}")
    return destino
