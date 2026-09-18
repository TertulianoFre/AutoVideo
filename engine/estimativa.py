"""Estimativa de quanto tempo um vídeo leva pra ficar pronto. As constantes vêm
de medições reais desse app; depois de cada vídeo gerado o fator de correção é
ajustado com o tempo que realmente levou (dados/tempos.json), então a estimativa
vai ficando mais certa com o uso."""

import json
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "dados" / "tempos.json"
SEGUNDOS_POR_CENA_MEDIA = 13  # duração típica de uma cena (5 cenas em ~1 min)
SEGUNDOS_POR_IMAGEM = {"ia": 14.0, "foto": 12.0, "procedural": 1.5}


def _fator() -> float:
    try:
        return float(json.loads(ARQUIVO.read_text(encoding="utf-8")).get("fator", 1.0))
    except (OSError, ValueError, TypeError):
        return 1.0


def estimar_bruto(p: dict) -> float:
    """Segundos SEM a correção aprendida. Chaves de `p` (todas opcionais):
    duracao_min, n_cenas, estilo_imagem, formatos, sem_narracao, tem_roteiro,
    narracao_propria, som_fundo, transicao, n_imagens_base."""
    duracao_min = max(0.3, float(p.get("duracao_min") or 1.0))
    dur_s = duracao_min * 60
    sem_narracao = bool(p.get("sem_narracao"))
    n_formatos = 2 if p.get("formatos", "ambos") == "ambos" else 1
    n_cenas = p.get("n_cenas") or (max(1, round(dur_s / 240)) if sem_narracao else max(2, round(dur_s / SEGUNDOS_POR_CENA_MEDIA)))

    t = 6.0
    if not sem_narracao:
        if not p.get("tem_roteiro"):
            t += 15 + 5 * duracao_min
        if not p.get("narracao_propria"):
            t += 4 + 3 * duracao_min
        t += 14  # hashtags + descrição do YouTube
    if p.get("som_fundo") or sem_narracao:
        t += 2 + duracao_min
    n_novas = max(0, n_cenas - min(int(p.get("n_imagens_base") or 0), n_cenas))
    t += n_novas * n_formatos * SEGUNDOS_POR_IMAGEM.get(p.get("estilo_imagem", "ia"), 14.0)
    render = max(4.0, 0.22 * dur_s) * n_formatos
    if p.get("transicao", "fade") != "nenhuma" and n_cenas > 1:
        render *= 1.3
    return t + render + 3


def estimar(p: dict) -> float:
    return estimar_bruto(p) * _fator()


def de_parametros_do_job(params: dict) -> dict:
    """Converte os parâmetros de gerar_video no formato de estimar_bruto."""
    return {
        "duracao_min": params.get("duracao_alvo_minutos"),
        "n_cenas": params.get("num_cenas"),
        "estilo_imagem": params.get("estilo_imagem", "ia"),
        "formatos": params.get("formatos", "ambos"),
        "sem_narracao": params.get("sem_narracao"),
        "tem_roteiro": bool(params.get("roteiro")),
        "narracao_propria": params.get("narracao_customizada"),
        "som_fundo": bool(params.get("som_fundo_tipo")),
        "transicao": params.get("transicao", "fade"),
        "n_imagens_base": len(params.get("imagens_base") or []),
    }


def registrar(bruto: float, real: float) -> None:
    """Aprende com um vídeo que terminou: mistura o erro dessa vez no fator (média móvel)."""
    if bruto <= 0 or real <= 0:
        return
    novo = min(5.0, max(0.3, 0.6 * _fator() + 0.4 * (real / bruto)))
    try:
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        ARQUIVO.write_text(json.dumps({"fator": round(novo, 3)}), encoding="utf-8")
    except OSError:
        pass
