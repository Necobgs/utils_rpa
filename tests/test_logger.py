import logging
import os
import time
from pathlib import Path

import pytest

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
    assert not (tmp_path / "custom.log.log").exists()
    file_handler = next(
        h for h in logger.handlers if isinstance(h, ConcurrentRotatingFileHandler)
    )
    assert file_handler.maxBytes == 1024
    assert file_handler.backupCount == 7


def test_configure_logger_name_none_uses_root_and_automation_log(tmp_path):
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    root.handlers.clear()
    try:
        logger = configure_logger(log_dir=tmp_path)
        assert logger is root
        logger.info("mensagem de teste")
        assert (tmp_path / "automation.log").exists()
    finally:
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)
        for handler in previous_handlers:
            root.addHandler(handler)


def test_configure_logger_file_name_without_extension_gets_log_suffix(tmp_path):
    logger = configure_logger(
        "test_rpa_stem",
        log_dir=tmp_path,
        file_name="sem_extensao",
    )
    logger.info("mensagem de teste")
    assert (tmp_path / "sem_extensao.log").exists()


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


def test_cleanup_logs_by_last_update_removes_oldest_group(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    old = tmp_path / "automation-id-1.log"
    old_backup = tmp_path / "automation-id-1.log.1"
    old_lock = tmp_path / "automation-id-1.lock"
    mid = tmp_path / "automation-id-2.log"
    new = tmp_path / "automation-id-3.log"
    _touch_with_age(old, 300)
    _touch_with_age(old_backup, 50)
    _touch_with_age(old_lock, 50)
    _touch_with_age(mid, 200)
    _touch_with_age(new, 100)

    removed = cleanup_logs_by_last_update(tmp_path, "automation", keep=2)

    assert set(removed) == {old, old_backup, old_lock}
    assert not old.exists()
    assert not old_backup.exists()
    assert not old_lock.exists()
    assert mid.exists()
    assert new.exists()


def test_cleanup_logs_by_last_update_accepts_log_suffix_in_file_name(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    old = tmp_path / "automation-id-1.log"
    new = tmp_path / "automation-id-2.log"
    _touch_with_age(old, 300)
    _touch_with_age(new, 100)

    removed = cleanup_logs_by_last_update(tmp_path, "automation.log", keep=1)

    assert removed == [old]
    assert not old.exists()
    assert new.exists()


def test_cleanup_logs_by_last_update_uses_lowest_backup_index_when_base_missing(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    low_index = tmp_path / "automation-id-1.log.1"
    high_index = tmp_path / "automation-id-1.log.3"
    other = tmp_path / "automation-id-2.log"
    _touch_with_age(low_index, 10)
    _touch_with_age(high_index, 900)
    _touch_with_age(other, 200)

    removed = cleanup_logs_by_last_update(tmp_path, "automation", keep=1)

    assert set(removed) == {other}
    assert low_index.exists()
    assert high_index.exists()
    assert not other.exists()


def test_cleanup_logs_by_last_update_treats_lock_only_as_oldest(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    lock = tmp_path / "automation-id-8.lock"
    base = tmp_path / "automation-id-9.log"
    _touch_with_age(lock, 1)
    _touch_with_age(base, 10)

    removed = cleanup_logs_by_last_update(tmp_path, "automation", keep=1)

    assert removed == [lock]
    assert not lock.exists()
    assert base.exists()


def test_cleanup_logs_by_last_update_tie_removes_smaller_id(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    smaller = tmp_path / "automation-id-4.log"
    larger = tmp_path / "automation-id-9.log"
    _touch_with_age(smaller, 100)
    _touch_with_age(larger, 100)

    removed = cleanup_logs_by_last_update(tmp_path, "automation", keep=1)

    assert removed == [smaller]
    assert not smaller.exists()
    assert larger.exists()


def test_cleanup_logs_by_last_update_keep_zero_removes_only_matching_stem(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    match = tmp_path / "automation-id-1.log"
    other = tmp_path / "other-id-1.log"
    leading_zero = tmp_path / "automation-id-007.log"
    match.write_text("a")
    other.write_text("b")
    leading_zero.write_text("c")

    removed = cleanup_logs_by_last_update(tmp_path, "automation", keep=0)

    assert removed == [match]
    assert not match.exists()
    assert other.exists()
    assert leading_zero.exists()


def test_cleanup_logs_by_last_update_keeps_all_when_under_limit(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    kept = tmp_path / "automation-id-1.log"
    kept.write_text("a")

    assert cleanup_logs_by_last_update(tmp_path, "automation", keep=3) == []
    assert kept.exists()


def test_cleanup_logs_by_last_update_missing_dir_returns_empty(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    assert cleanup_logs_by_last_update(tmp_path / "nao", "automation", keep=1) == []


def test_cleanup_logs_by_last_update_rejects_invalid_keep_and_empty_name(tmp_path):
    from utils_rpa.logger import cleanup_logs_by_last_update

    missing = tmp_path / "nao"
    with pytest.raises(ValueError, match="keep"):
        cleanup_logs_by_last_update(missing, "automation", keep=-1)
    with pytest.raises(ValueError, match="keep"):
        cleanup_logs_by_last_update(missing, "automation", keep=True)
    with pytest.raises(ValueError, match="file_name"):
        cleanup_logs_by_last_update(tmp_path, "", keep=1)
    assert not missing.exists()


def test_cleanup_logs_by_last_update_skips_id_that_remains_after_failure(tmp_path, monkeypatch, caplog):
    from utils_rpa.logger import cleanup_logs_by_last_update

    first = tmp_path / "automation-id-1.log"
    second = tmp_path / "automation-id-2.log"
    first.write_text("a")
    second.write_text("b")

    def _boom(self):
        raise OSError("arquivo em uso")

    monkeypatch.setattr(Path, "unlink", _boom)
    with caplog.at_level(logging.WARNING):
        removed = cleanup_logs_by_last_update(tmp_path, "automation", keep=0)

    assert removed == []
    assert first.exists()
    assert second.exists()
    assert any("automation-id-1.log" in message for message in caplog.messages)
    assert any("automation-id-2.log" in message for message in caplog.messages)


def _close_logger(name: str | None) -> None:
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def test_configure_logger_by_id_creates_id_file(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        logger = configure_logger_by_id("test_rpa_by_id_create", id=123, log_dir=tmp_path)
        logger.info("mensagem")
        assert (tmp_path / "test_rpa_by_id_create-id-123.log").exists()
        assert logger.name == "test_rpa_by_id_create"
    finally:
        _close_logger("test_rpa_by_id_create")


def test_configure_logger_by_id_uses_file_name_stem(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        configure_logger_by_id(
            "test_rpa_by_id_stem",
            id=8,
            log_dir=tmp_path,
            file_name="automation.log",
        )
        assert (tmp_path / "automation-id-8.log").exists()
        assert not (tmp_path / "test_rpa_by_id_stem-id-8.log").exists()
    finally:
        _close_logger("test_rpa_by_id_stem")


def test_configure_logger_by_id_name_none_uses_automation(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    root = logging.getLogger()
    previous = list(root.handlers)
    root.handlers.clear()
    try:
        logger = configure_logger_by_id(id=4, log_dir=tmp_path)
        assert logger is root
        assert (tmp_path / "automation-id-4.log").exists()
    finally:
        _close_logger(None)
        for handler in previous:
            root.addHandler(handler)


def test_configure_logger_by_id_rejects_invalid_id_before_mkdir(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    missing = tmp_path / "nao"
    for invalid in (0, -1, True, "1", 1.5):
        with pytest.raises(ValueError, match="id"):
            configure_logger_by_id("test_rpa_by_id_bad", id=invalid, log_dir=missing)
    assert not missing.exists()


def test_configure_logger_by_id_rejects_invalid_max_ids_and_empty_file_name(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    missing = tmp_path / "nao"
    with pytest.raises(ValueError, match="max_ids"):
        configure_logger_by_id("test_rpa_by_id_bad_max", id=1, log_dir=missing, max_ids=0)
    with pytest.raises(ValueError, match="max_ids"):
        configure_logger_by_id("test_rpa_by_id_bad_max", id=1, log_dir=missing, max_ids=True)
    with pytest.raises(ValueError, match="file_name"):
        configure_logger_by_id(
            "test_rpa_by_id_bad_name",
            id=1,
            log_dir=missing,
            file_name="",
        )
    assert not missing.exists()


def test_configure_logger_by_id_unlimited_backup_and_explicit_limit(tmp_path):
    from utils_rpa.logger import UNLIMITED_BACKUP_COUNT, configure_logger_by_id

    try:
        unlimited = configure_logger_by_id("test_rpa_by_id_unlim", id=1, log_dir=tmp_path)
        limited = configure_logger_by_id(
            "test_rpa_by_id_lim",
            id=1,
            log_dir=tmp_path,
            backup_count=4,
            max_bytes=1024,
        )
        unlimited_handler = next(
            handler
            for handler in unlimited.handlers
            if isinstance(handler, ConcurrentRotatingFileHandler)
        )
        limited_handler = next(
            handler
            for handler in limited.handlers
            if isinstance(handler, ConcurrentRotatingFileHandler)
        )
        assert unlimited_handler.backupCount == UNLIMITED_BACKUP_COUNT
        assert limited_handler.backupCount == 4
        assert limited_handler.maxBytes == 1024
    finally:
        _close_logger("test_rpa_by_id_unlim")
        _close_logger("test_rpa_by_id_lim")


def test_configure_logger_by_id_rollover_keeps_newest_backup_as_dot_1(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        logger = configure_logger_by_id(
            "test_rpa_by_id_roll",
            id=7,
            log_dir=tmp_path,
            max_bytes=80,
        )
        logger.info("FIRST-MARKER " + ("a" * 100))
        logger.info("SECOND-MARKER " + ("b" * 100))
        logger.info("THIRD-MARKER " + ("c" * 100))
        newest_backup = (tmp_path / "test_rpa_by_id_roll-id-7.log.1").read_text(encoding="utf-8")
        older_backup = (tmp_path / "test_rpa_by_id_roll-id-7.log.2").read_text(encoding="utf-8")
        assert "SECOND-MARKER" in newest_backup
        assert "FIRST-MARKER" in older_backup
    finally:
        _close_logger("test_rpa_by_id_roll")


def test_configure_logger_by_id_backup_count_discards_older_backups(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        logger = configure_logger_by_id(
            "test_rpa_by_id_discard",
            id=7,
            log_dir=tmp_path,
            max_bytes=80,
            backup_count=1,
        )
        logger.info("FIRST-MARKER " + ("a" * 100))
        logger.info("SECOND-MARKER " + ("b" * 100))
        logger.info("THIRD-MARKER " + ("c" * 100))
        assert (tmp_path / "test_rpa_by_id_discard-id-7.log.1").exists()
        assert not (tmp_path / "test_rpa_by_id_discard-id-7.log.2").exists()
    finally:
        _close_logger("test_rpa_by_id_discard")


def test_configure_logger_by_id_max_ids_removes_lowest_and_protects_current(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        _touch_with_age(tmp_path / "bot-id-50.log", 5000)
        _touch_with_age(tmp_path / "bot-id-2.log", 10)
        (tmp_path / "other-id-1.log").write_text("z")
        configure_logger_by_id("test_rpa_by_id_max", id=60, log_dir=tmp_path, file_name="bot.log", max_ids=2)
        assert not (tmp_path / "bot-id-2.log").exists()
        assert (tmp_path / "bot-id-50.log").exists()
        assert (tmp_path / "bot-id-60.log").exists()
        assert (tmp_path / "other-id-1.log").exists()
    finally:
        _close_logger("test_rpa_by_id_max")


def test_configure_logger_by_id_keeps_current_when_it_is_the_lowest(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        (tmp_path / "bot-id-5.log").write_text("a")
        (tmp_path / "bot-id-9.log").write_text("b")
        configure_logger_by_id("test_rpa_by_id_current", id=1, log_dir=tmp_path, file_name="bot", max_ids=2)
        assert (tmp_path / "bot-id-1.log").exists()
        assert not (tmp_path / "bot-id-5.log").exists()
        assert (tmp_path / "bot-id-9.log").exists()
    finally:
        _close_logger("test_rpa_by_id_current")


def test_configure_logger_by_id_without_max_ids_keeps_other_ids(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        (tmp_path / "bot-id-1.log").write_text("a")
        configure_logger_by_id("test_rpa_by_id_nomax", id=9, log_dir=tmp_path, file_name="bot")
        assert (tmp_path / "bot-id-1.log").exists()
    finally:
        _close_logger("test_rpa_by_id_nomax")


def test_configure_logger_by_id_repeat_does_not_duplicate_and_still_purges(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        logger = configure_logger_by_id(
            "test_rpa_by_id_repeat",
            id=5,
            log_dir=tmp_path,
            file_name="bot",
            max_ids=1,
        )
        handler_count = len(logger.handlers)
        (tmp_path / "bot-id-1.log").write_text("later")
        again = configure_logger_by_id(
            "test_rpa_by_id_repeat",
            id=5,
            log_dir=tmp_path,
            file_name="bot",
            max_ids=1,
            level=logging.DEBUG,
        )
        file_handlers = [
            handler
            for handler in again.handlers
            if isinstance(handler, ConcurrentRotatingFileHandler)
        ]
        assert again is logger
        assert len(again.handlers) == handler_count
        assert len(file_handlers) == 1
        assert again.level == logging.INFO
        assert not (tmp_path / "bot-id-1.log").exists()
    finally:
        _close_logger("test_rpa_by_id_repeat")


def test_configure_logger_by_id_switches_file_and_drops_previous_id(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        logger = configure_logger_by_id(
            "test_rpa_by_id_switch",
            id=123,
            log_dir=tmp_path,
            max_ids=1,
        )
        logger.info("linha-123")
        handler_count = len(logger.handlers)
        same = configure_logger_by_id(
            "test_rpa_by_id_switch",
            id=456,
            log_dir=tmp_path,
            max_ids=1,
            level=logging.DEBUG,
            log_format="SOMENTE %(message)s",
        )
        same.info("linha-456")
        file_handlers = [
            handler
            for handler in same.handlers
            if isinstance(handler, ConcurrentRotatingFileHandler)
        ]
        text_456 = (tmp_path / "test_rpa_by_id_switch-id-456.log").read_text(encoding="utf-8")
        assert same is logger
        assert same.level == logging.INFO
        assert len(same.handlers) == handler_count
        assert len(file_handlers) == 1
        assert "SOMENTE" not in text_456
        assert "|" in text_456
        assert not (tmp_path / "test_rpa_by_id_switch-id-123.log").exists()
        assert "linha-456" in text_456
        assert "linha-123" not in text_456
    finally:
        _close_logger("test_rpa_by_id_switch")


def test_configure_logger_by_id_different_names_write_separate_files(tmp_path):
    from utils_rpa.logger import configure_logger_by_id

    try:
        first = configure_logger_by_id("test_rpa_by_id_a", id=1, log_dir=tmp_path)
        second = configure_logger_by_id("test_rpa_by_id_b", id=2, log_dir=tmp_path)
        first.info("texto-a")
        second.info("texto-b")
        assert "texto-a" in (tmp_path / "test_rpa_by_id_a-id-1.log").read_text(encoding="utf-8")
        assert "texto-b" in (tmp_path / "test_rpa_by_id_b-id-2.log").read_text(encoding="utf-8")
    finally:
        _close_logger("test_rpa_by_id_a")
        _close_logger("test_rpa_by_id_b")


def test_configure_logger_after_by_id_does_not_switch_file(tmp_path):
    from utils_rpa import configure_logger
    from utils_rpa.logger import configure_logger_by_id

    try:
        logger = configure_logger_by_id("test_rpa_by_id_sticky", id=4, log_dir=tmp_path)
        configure_logger("test_rpa_by_id_sticky", log_dir=tmp_path, file_name="outro.log")
        logger.info("continua-no-id")
        assert "continua-no-id" in (tmp_path / "test_rpa_by_id_sticky-id-4.log").read_text(
            encoding="utf-8"
        )
        assert not (tmp_path / "outro.log").exists()
    finally:
        _close_logger("test_rpa_by_id_sticky")


def test_configure_logger_by_id_warns_and_continues_when_delete_fails(tmp_path, monkeypatch, caplog):
    from utils_rpa.logger import configure_logger_by_id

    (tmp_path / "bot-id-1.log").write_text("a")

    def _boom(self):
        raise OSError("arquivo em uso")

    monkeypatch.setattr(Path, "unlink", _boom)
    try:
        with caplog.at_level(logging.WARNING):
            logger = configure_logger_by_id(
                "test_rpa_by_id_warn",
                id=9,
                log_dir=tmp_path,
                file_name="bot",
                max_ids=1,
            )
        assert logger.name == "test_rpa_by_id_warn"
        assert (tmp_path / "bot-id-1.log").exists()
        assert any("bot-id-1.log" in message for message in caplog.messages)
    finally:
        _close_logger("test_rpa_by_id_warn")


def test_logger_by_id_functions_are_exported():
    import utils_rpa
    from utils_rpa.logger import cleanup_logs_by_last_update, configure_logger_by_id

    assert utils_rpa.cleanup_logs_by_last_update is cleanup_logs_by_last_update
    assert utils_rpa.configure_logger_by_id is configure_logger_by_id
