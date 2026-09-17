"""Testa o motor de geração de vídeo pelo terminal.

Uso:
    .venv\\Scripts\\python cli.py --titulo "..." --roteiro "..." [--idioma pt-BR] [--voz mulher] [--duracao-alvo 5]
"""

import argparse

from engine.pipeline import gerar_video


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera um vídeo (16:9 e Shorts) a partir de um roteiro.")
    parser.add_argument("--titulo", required=True)
    parser.add_argument("--roteiro", required=True)
    parser.add_argument("--idioma", default="pt-BR")
    parser.add_argument("--voz", default="mulher", choices=["mulher", "homem", "crianca"])
    parser.add_argument("--imagem", default="procedural", choices=["procedural", "foto", "ia"])
    parser.add_argument("--duracao-alvo", type=float, default=None, help="duração desejada, em minutos")
    args = parser.parse_args()

    resultado = gerar_video(args.titulo, args.roteiro, args.idioma, args.voz, args.imagem, args.duracao_alvo)

    minutos, segundos = divmod(round(resultado.duracao_segundos), 60)
    print(f"Pronto! Duração: {minutos}:{segundos:02d} — arquivos em: {resultado.pasta}")
    print(f"  16:9  -> {resultado.video_16_9}")
    print(f"  9:16  -> {resultado.video_9_16}")


if __name__ == "__main__":
    main()
