"""Configuração de logging para automações de RPA."""

from __future__ import annotations

import logging
from pathlib import Path

from concurrent_log_handler import ConcurrentRotatingFileHandler

DEFAULT_LOG_DIR = "./logs"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_BACKUP_COUNT = 3
DEFAULT_LEVEL = logging.INFO
DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

__all__ = [
    "configure_logger",
    "DEFAULT_LOG_DIR",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_BACKUP_COUNT",
]


def configure_logger(
    name: str = '__main__',
    *,
    log_dir: str | Path = DEFAULT_LOG_DIR,
    file_name: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    level: int = DEFAULT_LEVEL,
    log_format: str = DEFAULT_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
) -> logging.Logger:
    """Cria e configura um logger com saída para console e arquivo rotativo.

    O arquivo de log usa ``ConcurrentRotatingFileHandler`` (seguro para
    múltiplos processos/threads), com rotação por tamanho.

    Args:
        name: Nome do logger. Por padrão, o nome do módulo (``"__main__"``).
        log_dir: Diretório onde os arquivos de log serão salvos. Criado se
            não existir. Padrão: ``./logs``.
        file_name: Nome do arquivo de log. Se ``None``, usa ``<name>.log``.
        max_bytes: Tamanho máximo do arquivo antes de rotacionar, em bytes.
            Padrão: 5 MB.
        backup_count: Quantidade de arquivos de backup mantidos. Padrão: 3.
        level: Nível de log. Padrão: ``logging.INFO``.
        log_format: Formato das mensagens de log.
        date_format: Formato do ``asctime`` (data/hora), sem milissegundos.
            Padrão: ``%Y-%m-%d %H:%M:%S`` (ano-mês-dia hora:minuto:segundo).

    Returns:
        O logger configurado.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Evita adicionar handlers duplicados se a função for chamada mais de uma
    # vez para o mesmo logger.
    if logger.handlers:
        return logger

    formatter = logging.Formatter(log_format, datefmt=date_format)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    file_path = log_path / (file_name or f"{name}.log")
    file_handler = ConcurrentRotatingFileHandler(
        str(file_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
