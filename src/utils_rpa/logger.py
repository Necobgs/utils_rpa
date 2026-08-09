"""Configuração de logging para automações de RPA."""

from __future__ import annotations

import logging
import sys
import time
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
    "cleanup_old_logs",
    "DEFAULT_LOG_DIR",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_BACKUP_COUNT",
]


def cleanup_old_logs(
    log_dir: str | Path,
    max_age_days: int,
    *,
    logger: logging.Logger | None = None,
) -> list[Path]:
    """Remove arquivos ``.log``/``.lock`` de ``log_dir`` mais antigos que ``max_age_days``.

    Considera apenas o nível superior de ``log_dir`` (sem recursão em
    subpastas). A idade é calculada pela data de última modificação
    (``mtime``) do arquivo.

    Args:
        log_dir: Diretório a ser varrido. Se não existir, retorna lista vazia.
        max_age_days: Idade máxima, em dias. Arquivos mais antigos são
            removidos.
        logger: Logger usado para registrar falhas de exclusão. Se ``None``,
            usa o logger do próprio módulo.

    Returns:
        Lista dos caminhos efetivamente removidos.
    """
    log = logger or logging.getLogger(__name__)
    path = Path(log_dir)
    if not path.is_dir():
        return []

    cutoff = time.time() - max_age_days * 86400
    candidates = set(path.glob("*.log*")) | set(path.glob("*.lock"))

    removed: list[Path] = []
    for file_path in candidates:
        if not file_path.is_file():
            continue
        try:
            if file_path.stat().st_mtime >= cutoff:
                continue
            file_path.unlink()
            removed.append(file_path)
        except OSError as exc:
            log.warning("Não foi possível excluir o log antigo '%s': %s", file_path, exc)

    return removed


def configure_logger(
    name: str = '__main__',
    *,
    log_dir: str | Path = DEFAULT_LOG_DIR,
    file_name: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    max_age_days: int | None = None,
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
        max_age_days: Se informado, arquivos ``.log``/``.lock`` em ``log_dir``
            com mais dias que esse valor são excluídos ao configurar o
            logger. Padrão: ``None`` (nenhuma limpeza).
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

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(lambda record: record.levelno < logging.ERROR)
    logger.addHandler(console_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(logging.ERROR)
    logger.addHandler(stderr_handler)

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    if max_age_days is not None:
        cleanup_old_logs(log_path, max_age_days, logger=logger)

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
