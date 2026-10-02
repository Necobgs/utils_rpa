"""Configuração de logging para automações de RPA."""

from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path

from concurrent_log_handler import ConcurrentRotatingFileHandler

DEFAULT_LOG_DIR = "./logs"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_BACKUP_COUNT = 3
DEFAULT_LEVEL = logging.INFO
DEFAULT_FORMAT = "%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s"
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


def _log_stem(file_name: str) -> str:
    if file_name.endswith(".log"):
        return file_name[:-4]
    return file_name


def _id_patterns(stem: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    escaped = re.escape(stem)
    file_re = re.compile(rf"^{escaped}-id-([1-9]\d*)\.log(?:\.(\d+))?$")
    lock_re = re.compile(rf"^{escaped}-id-([1-9]\d*)\.lock$")
    return file_re, lock_re


def _iter_log_id_groups(log_dir: Path, stem: str) -> dict[int, list[Path]]:
    file_re, lock_re = _id_patterns(stem)
    groups: dict[int, list[Path]] = {}
    if not log_dir.is_dir():
        return groups
    for entry in log_dir.iterdir():
        if not entry.is_file():
            continue
        match = file_re.match(entry.name) or lock_re.match(entry.name)
        if match is None:
            continue
        groups.setdefault(int(match.group(1)), []).append(entry)
    return groups


def _group_age_key(stem: str, log_id: int, files: list[Path]) -> tuple[int, float, int]:
    file_re, _lock_re = _id_patterns(stem)
    base_mtime: float | None = None
    lowest_backup: tuple[int, float] | None = None
    for file_path in files:
        match = file_re.match(file_path.name)
        if match is None:
            continue
        backup_index = match.group(2)
        mtime = file_path.stat().st_mtime
        if backup_index is None:
            base_mtime = mtime
            continue
        index = int(backup_index)
        if lowest_backup is None or index < lowest_backup[0]:
            lowest_backup = (index, mtime)
    if base_mtime is not None:
        return (1, base_mtime, log_id)
    if lowest_backup is not None:
        return (1, lowest_backup[1], log_id)
    return (0, 0.0, log_id)


def _delete_log_files(files: list[Path], logger: logging.Logger) -> list[Path]:
    removed: list[Path] = []
    for file_path in files:
        try:
            file_path.unlink()
        except OSError as exc:
            logger.warning(
                "Não foi possível excluir o log antigo '%s': %s",
                file_path,
                exc,
            )
        else:
            removed.append(file_path)
    return removed


def cleanup_logs_by_last_update(
    log_dir: str | Path,
    file_name: str,
    keep: int,
    *,
    logger: logging.Logger | None = None,
) -> list[Path]:
    """Remove grupos de log por id até sobrar ``keep`` grupos, dos mais antigos para os mais novos.

    A data de um grupo é o ``mtime`` de ``{stem}-id-{id}.log``. Se esse arquivo
    não existir, usa o ``mtime`` do backup de menor índice. Um id que só tem
    ``.lock`` é tratado como o mais antigo. Empate de data remove o menor id.

    Args:
        log_dir: Pasta dos logs. Se não existir, retorna lista vazia.
        file_name: Nome-base. ``automation`` e ``automation.log`` casam os mesmos grupos.
        keep: Quantidade de ids que permanecem. ``0`` remove todos os grupos do stem.
        logger: Logger dos warnings de falha. Se ``None``, usa o logger do módulo.

    Returns:
        Caminhos efetivamente removidos.
    """
    if isinstance(keep, bool) or not isinstance(keep, int) or keep < 0:
        raise ValueError("keep deve ser um inteiro maior ou igual a zero")
    if file_name == "":
        raise ValueError("file_name não pode ser vazio")

    log = logger or logging.getLogger(__name__)
    path = Path(log_dir)
    if not path.is_dir():
        return []

    stem = _log_stem(file_name)
    removed: list[Path] = []
    skipped: set[int] = set()
    while True:
        groups = _iter_log_id_groups(path, stem)
        if len(groups) <= keep:
            return removed
        candidates = [log_id for log_id in groups if log_id not in skipped]
        if not candidates:
            return removed
        victim = min(
            candidates,
            key=lambda log_id: _group_age_key(stem, log_id, groups[log_id]),
        )
        deleted = _delete_log_files(groups[victim], log)
        removed.extend(deleted)
        if any(file_path.exists() for file_path in groups[victim]):
            skipped.add(victim)


def configure_logger(
    name: str | None = None,
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
        name: Nome do logger. Se ``None``, usa o logger root (``logging.getLogger()``).
        log_dir: Diretório onde os arquivos de log serão salvos. Criado se
            não existir. Padrão: ``./logs``.
        file_name: Nome do arquivo de log. Se ``None``, usa ``<name>.log``;
            se ``name`` também for ``None``, usa ``automation.log``. Se o
            valor já terminar com ``.log``, a extensão não é duplicada.
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

    resolved_file_name = file_name or name or "automation"
    if not resolved_file_name.endswith(".log"):
        resolved_file_name = f"{resolved_file_name}.log"
    file_path = log_path / resolved_file_name
    file_handler = ConcurrentRotatingFileHandler(
        str(file_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
