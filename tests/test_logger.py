import logging
import os
import time
from pathlib import Path

from concurrent_log_handler import ConcurrentRotatingFileHandler

from utils_rpa import configure_logger
from utils_rpa.logger import DEFAULT_BACKUP_COUNT, DEFAULT_MAX_BYTES, cleanup_old_logs


def _touch_with_age(path, age_seconds):
    path.write_text("conteudo")
    old_time = time.time() - age_seconds
    os.utime(path, (old_time, old_time))


def test_configure_logger_creates_console_and_file_handlers(tmp_path):
    logger = configure_logger("test_rpa_console_file", log_dir=tmp_path)

    handler_types = [type(h) for h in logger.handlers]
    assert logging.StreamHandler in handler_types
    assert any(isinstance(h, ConcurrentRotatingFileHandler) for h in logger.handlers)


def test_configure_logger_creates_directory_and_file(tmp_path):
    log_dir = tmp_path / "logs"
    logger = configure_logger("test_rpa_file", log_dir=log_dir)
    logger.info("mensagem de teste")

    assert log_dir.exists()
    assert (log_dir / "test_rpa_file.log").exists()


def test_configure_logger_uses_defaults(tmp_path):
    logger = configure_logger("test_rpa_defaults", log_dir=tmp_path)

    file_handler = next(
        h for h in logger.handlers if isinstance(h, ConcurrentRotatingFileHandler)
    )
    assert file_handler.maxBytes == DEFAULT_MAX_BYTES
    assert file_handler.backupCount == DEFAULT_BACKUP_COUNT


def test_configure_logger_custom_parameters(tmp_path):
    logger = configure_logger(
        "test_rpa_custom",
        log_dir=tmp_path,
        file_name="custom.log",
        max_bytes=1024,
        backup_count=7,
        level=logging.DEBUG,
    )

    logger.debug("mensagem de teste")

    assert logger.level == logging.DEBUG
    assert (tmp_path / "custom.log").exists()
    file_handler = next(
        h for h in logger.handlers if isinstance(h, ConcurrentRotatingFileHandler)
    )
    assert file_handler.maxBytes == 1024
    assert file_handler.backupCount == 7


def test_configure_logger_does_not_duplicate_handlers(tmp_path):
    logger1 = configure_logger("test_rpa_no_duplicate", log_dir=tmp_path)
    initial_count = len(logger1.handlers)

    logger2 = configure_logger("test_rpa_no_duplicate", log_dir=tmp_path)

    assert logger1 is logger2
    assert len(logger2.handlers) == initial_count


def test_cleanup_old_logs_removes_files_older_than_max_age(tmp_path):
    old_log = tmp_path / "bot.log.1"
    old_lock = tmp_path / "bot.log.lock"
    _touch_with_age(old_log, age_seconds=10 * 86400)
    _touch_with_age(old_lock, age_seconds=10 * 86400)

    removed = cleanup_old_logs(tmp_path, max_age_days=5)

    assert set(removed) == {old_log, old_lock}
    assert not old_log.exists()
    assert not old_lock.exists()


def test_cleanup_old_logs_keeps_recent_files(tmp_path):
    recent_log = tmp_path / "bot.log"
    _touch_with_age(recent_log, age_seconds=60)

    removed = cleanup_old_logs(tmp_path, max_age_days=5)

    assert removed == []
    assert recent_log.exists()


def test_cleanup_old_logs_ignores_unrelated_extensions(tmp_path):
    unrelated = tmp_path / "notes.txt"
    _touch_with_age(unrelated, age_seconds=10 * 86400)

    removed = cleanup_old_logs(tmp_path, max_age_days=5)

    assert removed == []
    assert unrelated.exists()


def test_cleanup_old_logs_returns_empty_list_when_dir_missing(tmp_path):
    missing_dir = tmp_path / "nao_existe"

    assert cleanup_old_logs(missing_dir, max_age_days=5) == []


def test_cleanup_old_logs_logs_warning_on_deletion_failure(tmp_path, monkeypatch, caplog):
    old_log = tmp_path / "bot.log.1"
    _touch_with_age(old_log, age_seconds=10 * 86400)

    def _boom(self):
        raise OSError("arquivo em uso")

    monkeypatch.setattr(Path, "unlink", _boom)

    with caplog.at_level(logging.WARNING):
        removed = cleanup_old_logs(tmp_path, max_age_days=5)

    assert removed == []
    assert any("bot.log.1" in m for m in caplog.messages)


def test_configure_logger_cleans_old_files_when_max_age_days_set(tmp_path):
    old_backup = tmp_path / "outro_bot.log.1"
    _touch_with_age(old_backup, age_seconds=10 * 86400)

    configure_logger("test_rpa_cleanup", log_dir=tmp_path, max_age_days=5)

    assert not old_backup.exists()


def test_configure_logger_keeps_files_when_max_age_days_is_none(tmp_path):
    old_backup = tmp_path / "outro_bot.log.1"
    _touch_with_age(old_backup, age_seconds=10 * 86400)

    configure_logger("test_rpa_no_cleanup", log_dir=tmp_path)

    assert old_backup.exists()
