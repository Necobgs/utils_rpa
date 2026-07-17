import asyncio
import logging

import pytest

from utils_rpa import retry_with_logging


def test_retry_returns_success_without_retry():
    calls = {"n": 0}

    @retry_with_logging(attempts=3, delay=0)
    def always_ok():
        calls["n"] += 1
        return "ok"

    assert always_ok() == "ok"
    assert calls["n"] == 1


def test_retry_reruns_until_success():
    calls = {"n": 0}

    @retry_with_logging(attempts=5, delay=0)
    def fails_twice():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("ainda nao")
        return "ok"

    assert fails_twice() == "ok"
    assert calls["n"] == 3


def test_retry_exhausts_attempts_and_propagates_exception():
    calls = {"n": 0}

    @retry_with_logging(attempts=4, delay=0)
    def always_fails():
        calls["n"] += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        always_fails()
    assert calls["n"] == 4


def test_retry_logs_when_use_log_true(caplog):
    @retry_with_logging("retry_logger_test", attempts=2, delay=0)
    def fails():
        raise ValueError("erro")

    with caplog.at_level(logging.WARNING, logger="retry_logger_test"):
        with pytest.raises(ValueError):
            fails()

    assert any("falhou" in m for m in caplog.messages)


def test_retry_does_not_log_when_use_log_false(caplog):
    @retry_with_logging("retry_logger_no_log", attempts=2, delay=0, use_log=False)
    def fails():
        raise ValueError("erro")

    with caplog.at_level(logging.DEBUG, logger="retry_logger_no_log"):
        with pytest.raises(ValueError):
            fails()

    assert caplog.messages == []


def test_retry_invalid_attempts():
    with pytest.raises(ValueError, match="attempts"):

        @retry_with_logging(attempts=0)
        def _():
            pass


def test_async_retry_returns_success_without_retry():
    calls = {"n": 0}

    @retry_with_logging(attempts=3, delay=0)
    async def always_ok():
        calls["n"] += 1
        return "ok"

    assert asyncio.run(always_ok()) == "ok"
    assert calls["n"] == 1


def test_async_retry_reruns_until_success():
    calls = {"n": 0}

    @retry_with_logging(attempts=5, delay=0)
    async def fails_twice():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("ainda nao")
        return "ok"

    assert asyncio.run(fails_twice()) == "ok"
    assert calls["n"] == 3


def test_async_retry_exhausts_attempts_and_propagates_exception():
    calls = {"n": 0}

    @retry_with_logging(attempts=4, delay=0)
    async def always_fails():
        calls["n"] += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(always_fails())
    assert calls["n"] == 4


def test_async_retry_logs_when_use_log_true(caplog):
    @retry_with_logging("retry_async_logger_test", attempts=2, delay=0)
    async def fails():
        raise ValueError("erro")

    with caplog.at_level(logging.WARNING, logger="retry_async_logger_test"):
        with pytest.raises(ValueError):
            asyncio.run(fails())

    assert any("falhou" in m for m in caplog.messages)


def test_async_retry_does_not_log_when_use_log_false(caplog):
    @retry_with_logging("retry_async_logger_no_log", attempts=2, delay=0, use_log=False)
    async def fails():
        raise ValueError("erro")

    with caplog.at_level(logging.DEBUG, logger="retry_async_logger_no_log"):
        with pytest.raises(ValueError):
            asyncio.run(fails())

    assert caplog.messages == []
