"""Captura de tela (screenshot) da tela inteira do computador.

Usa a biblioteca ``mss`` para capturar toda a área de trabalho — incluindo o
navegador que estiver aberto, seja qual for. Por padrão captura todos os
monitores combinados; é possível escolher um monitor específico.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

# Índice usado pelo mss para representar a área que engloba TODOS os monitores.
ALL_MONITORS = 0

DEFAULT_SCREENSHOT_DIR = "./screenshots"

__all__ = ["capture_screen", "DEFAULT_SCREENSHOT_DIR", "ALL_MONITORS"]


def _get_logger(logger: logging.Logger | None) -> logging.Logger:
    return logger if logger is not None else logging.getLogger(__name__)


def capture_screen(
    output_path: str | Path | None = None,
    *,
    monitor: int = ALL_MONITORS,
    output_dir: str | Path = DEFAULT_SCREENSHOT_DIR,
    file_name: str | None = None,
    logger: logging.Logger | None = None,
) -> Path:
    """Captura um print da tela inteira do computador e salva em um arquivo PNG.

    Args:
        output_path: Caminho completo do arquivo de saída. Se informado, tem
            prioridade sobre ``output_dir``/``file_name``.
        monitor: Índice do monitor a capturar. ``0`` (padrão) captura todos os
            monitores combinados; ``1`` é o monitor principal, ``2`` o segundo,
            e assim por diante.
        output_dir: Diretório onde o arquivo será salvo quando ``output_path``
            não for informado. Criado se não existir. Padrão: ``./screenshots``.
        file_name: Nome do arquivo. Se ``None``, gera um nome com timestamp
            (ex.: ``screenshot_20260702_112500_123456.png``).
        logger: Logger opcional. Se ``None``, usa ``logging.getLogger(__name__)``.

    Returns:
        O caminho (``Path``) do arquivo de screenshot gerado.
    """
    import mss
    import mss.tools

    logger = _get_logger(logger)

    if output_path is not None:
        path = Path(output_path)
    else:
        if file_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            file_name = f"screenshot_{timestamp}.png"
        path = Path(output_dir) / file_name

    path.parent.mkdir(parents=True, exist_ok=True)

    with mss.mss() as sct:
        region = sct.monitors[monitor]
        shot = sct.grab(region)
        mss.tools.to_png(shot.rgb, shot.size, output=str(path))

    logger.info(f"[capture_screen] Screenshot salvo em: {path}")
    return path
