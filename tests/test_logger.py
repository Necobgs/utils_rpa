import logging

from concurrent_log_handler import ConcurrentRotatingFileHandler

from utils_rpa import configure_logger
from utils_rpa.logger import DEFAULT_BACKUP_COUNT, DEFAULT_MAX_BYTES


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
