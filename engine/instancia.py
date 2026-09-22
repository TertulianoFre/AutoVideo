"""Só UM servidor por vez cuida do trabalho de fundo (publicar no YouTube, importar a pasta de entrada).

Se por engano houver dois servidores abertos (ex.: um antigo que ficou na porta 8080 e um novo), cada um teria o seu
agendador e o mesmo vídeo seria publicado duas vezes. Aqui os servidores disputam um bloqueio de arquivo: quem tem o
bloqueio trabalha; o outro só serve as páginas e assume se o primeiro fechar. O sistema libera o bloqueio sozinho
quando o processo termina (mesmo se travar)."""

import msvcrt
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent.parent / "dados" / ".servidor.lock"
_arquivo = None  # fica aberto enquanto este processo for o principal


def tem_o_comando() -> bool:
    """True se este processo é o servidor que faz o trabalho de fundo. Pode ser chamada a cada ciclo: quem ainda não
    tem o comando tenta de novo (o outro pode ter fechado)."""
    global _arquivo
    if _arquivo is not None:
        return True
    try:
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        arquivo = open(ARQUIVO, "a+")
        arquivo.seek(0)
        msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        try:
            arquivo.close()
        except Exception:
            pass
        return False
    _arquivo = arquivo
    return True
