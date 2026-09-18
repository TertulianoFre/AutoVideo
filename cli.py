"""Testa o motor de geração de vídeo pelo terminal.

Uso:
    .venv\\Scripts\\python cli.py --titulo "..." --roteiro "..." [--idioma pt-BR] [--voz mulher] [--duracao-alvo 5]

Se você não passar --roteiro, o motor escreve um roteiro automaticamente a
partir do título, do tamanho certo pra bater --duracao-alvo (padrão: 1 minuto).
"""

import argparse
import sys

# Texto gerado por IA às vezes traz pontuação Unicode especial que quebra o
# print() no console do Windows (codepage padrão não sabe codificar).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from engine.ambiente import TIPOS_SUPORTADOS
from engine.pipeline import gerar_video


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera um vídeo (16:9 e Shorts) a partir de um título ou roteiro.")
    parser.add_argument("--titulo", required=True)
    parser.add_argument("--roteiro", default=None, help="se não passar, o roteiro é gerado automaticamente")
    parser.add_argument("--idioma", default="pt-BR")
    parser.add_argument("--voz", default="mulher", choices=["mulher", "homem", "crianca"])
    parser.add_argument("--imagem", default="procedural", choices=["procedural", "foto", "ia"])
    parser.add_argument("--duracao-alvo", type=float, default=None, help="duração desejada, em minutos")
    parser.add_argument("--descricao", default="", help="descrição livre: estilo visual, tom (ex: '2D infantil')")
    parser.add_argument("--sem-narracao", action="store_true", help="vídeo só com som de fundo, sem fala")
    parser.add_argument("--som-fundo", default="", choices=["", *TIPOS_SUPORTADOS], help="som de fundo (baixo, por baixo da narração; ou o áudio inteiro se --sem-narracao)")
    args = parser.parse_args()

    resultado = gerar_video(
        args.titulo,
        args.roteiro,
        args.idioma,
        args.voz,
        args.imagem,
        args.duracao_alvo,
        descricao_video=args.descricao,
        sem_narracao=args.sem_narracao,
        som_fundo_tipo=args.som_fundo,
    )

    minutos, segundos = divmod(round(resultado.duracao_segundos), 60)
    print(f"Pronto! Duração: {minutos}:{segundos:02d} — arquivos em: {resultado.pasta}")
    print(f"  16:9  -> {resultado.video_16_9}")
    print(f"  9:16  -> {resultado.video_9_16}")


if __name__ == "__main__":
    main()
