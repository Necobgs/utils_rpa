# Async `retry_with_logging` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extender `@retry_with_logging` para detectar `async def` e retornar um wrapper async com `asyncio.sleep`, sem quebrar o caminho sync.

**Architecture:** No decorate-time, `inspect.iscoroutinefunction(func)` escolhe entre wrapper sync (atual, `time.sleep`) e wrapper async (`await func(...)`, `asyncio.sleep`). Mesma API pública e mesmas mensagens de log.

**Tech Stack:** Python >=3.12, `asyncio`, `inspect`, `functools`, pytest (testes async via `asyncio.run`, sem `pytest-asyncio`).

## Global Constraints

- API única: `@retry_with_logging` (sem decorator separado)
- Sem mudanças em `anti_captcha`
- Sem adicionar `pytest-asyncio`
- Defaults inalterados: `attempts=5`, `delay=1.0`, `use_log=True`, `logger_name="__main__"`
- Spec: `docs/superpowers/specs/2026-07-17-async-retry-with-logging-design.md`

---

## File Structure

| Arquivo | Responsabilidade |
|---------|------------------|
| `src/utils_rpa/retry.py` | Decorator com wrappers sync e async |
| `tests/test_retry.py` | Testes sync (existentes) + novos async |
| `README.md` | Exemplo de uso async |

---

### Task 1: Testes async (TDD — falham antes da implementação)

**Files:**
- Modify: `tests/test_retry.py`
- Test: `tests/test_retry.py`

**Interfaces:**
- Consumes: `retry_with_logging` de `utils_rpa` (assinatura atual)
- Produces: testes async que exigem wrapper awaitable

- [ ] **Step 1: Acrescentar testes async ao final de `tests/test_retry.py`**

```python
import asyncio


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
```

Colocar `import asyncio` no topo do arquivo junto aos outros imports.

- [ ] **Step 2: Rodar testes async e confirmar falha**

Run: `pytest tests/test_retry.py -k async -v`

Expected: FAIL (ex.: `RuntimeWarning: coroutine ... was never awaited` e/ou assertion error — o wrapper atual é sync e não faz `await` na coroutine).

- [ ] **Step 3: Commit dos testes**

```bash
git add tests/test_retry.py
git commit -m "test: add async cases for retry_with_logging"
```

---

### Task 2: Implementar wrapper async em `retry.py`

**Files:**
- Modify: `src/utils_rpa/retry.py`
- Test: `tests/test_retry.py`

**Interfaces:**
- Consumes: assinatura pública atual de `retry_with_logging`
- Produces: decorator que, para `async def`, retorna `Callable[..., Awaitable[T]]`; para `def`, `Callable[..., T]`

- [ ] **Step 1: Substituir o corpo de `retry.py` pela implementação com dual wrapper**

```python
"""Decorator de retentativa (retry) com logging integrado."""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

DEFAULT_ATTEMPTS = 5
DEFAULT_DELAY = 1.0

__all__ = ["retry_with_logging", "DEFAULT_ATTEMPTS", "DEFAULT_DELAY"]


def retry_with_logging(
    logger_name: str = "__main__",
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    delay: float = DEFAULT_DELAY,
    use_log: bool = True,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator que reexecuta a função em caso de exceção, registrando logs.

    Funciona com funções sync e ``async def``. No caminho async, o delay
    usa ``asyncio.sleep``.

    Args:
        logger_name: Nome do logger usado para registrar as tentativas. Por
            padrão, ``__main__``.
        attempts: Número máximo de tentativas. Padrão: 5.
        delay: Segundos de espera entre as tentativas. Padrão: 1.0.
        use_log: Se ``True``, registra as tentativas e falhas no logger.
            Padrão: ``True``.

    Returns:
        O decorator configurado.

    Raises:
        ValueError: Se ``attempts`` for menor que 1.
    """
    if attempts < 1:
        raise ValueError("'attempts' deve ser maior ou igual a 1.")

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: object, **kwargs: object) -> T:
                logger = logging.getLogger(logger_name) if use_log else None
                last_exc: BaseException | None = None

                for attempt in range(1, attempts + 1):
                    try:
                        return await func(*args, **kwargs)  # type: ignore[misc]
                    except Exception as exc:
                        last_exc = exc
                        if logger is not None:
                            logger.warning(
                                "Tentativa %d/%d de '%s' falhou: %s",
                                attempt,
                                attempts,
                                func.__name__,
                                exc,
                            )
                        if attempt < attempts:
                            await asyncio.sleep(delay)

                if logger is not None:
                    logger.error(
                        "Todas as %d tentativas de '%s' falharam.",
                        attempts,
                        func.__name__,
                    )
                assert last_exc is not None
                raise last_exc

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def wrapper(*args: object, **kwargs: object) -> T:
            logger = logging.getLogger(logger_name) if use_log else None
            last_exc: BaseException | None = None

            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if logger is not None:
                        logger.warning(
                            "Tentativa %d/%d de '%s' falhou: %s",
                            attempt,
                            attempts,
                            func.__name__,
                            exc,
                        )
                    if attempt < attempts:
                        time.sleep(delay)

            if logger is not None:
                logger.error(
                    "Todas as %d tentativas de '%s' falharam.",
                    attempts,
                    func.__name__,
                )
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator
```

Nota: se `Awaitable` ficar sem uso após a implementação, remover do import para satisfazer o ruff (`F401`).

- [ ] **Step 2: Rodar a suíte completa de retry**

Run: `pytest tests/test_retry.py -v`

Expected: todos PASS (sync + async).

- [ ] **Step 3: Commit da implementação**

```bash
git add src/utils_rpa/retry.py
git commit -m "feat: support async functions in retry_with_logging"
```

---

### Task 3: Documentar uso async no README

**Files:**
- Modify: `README.md` (seção `### \`retry_with_logging\``, após o bloco "Sem logging")

**Interfaces:**
- Consumes: API de `retry_with_logging` já implementada
- Produces: documentação de uso async

- [ ] **Step 1: Inserir exemplo async após o bloco "Sem logging"**

Após:

````markdown
```python
@retry_with_logging(attempts=5, delay=1, use_log=False)
def tarefa_silenciosa():
    ...
```
````

Inserir:

````markdown

Com função assíncrona (o delay usa `asyncio.sleep`):

```python
@retry_with_logging("meu_bot", attempts=3, delay=2)
async def baixar_relatorio_async():
    return await http_get_async("https://exemplo/relatorio")

relatorio = await baixar_relatorio_async()
```
````

Também atualizar a frase introdutória da seção para mencionar suporte async, por exemplo:

```markdown
Decorator que reexecuta a função (sync ou `async def`) quando ela lança uma exceção, registrando cada tentativa no logger. Defaults: 5 tentativas, 1 segundo entre elas, logging ativado.
```

- [ ] **Step 2: Commit da documentação**

```bash
git add README.md
git commit -m "docs: document async usage of retry_with_logging"
```

---

## Self-Review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| API única com detecção decorate-time | Task 2 |
| `asyncio.sleep` no caminho async | Task 2 |
| `time.sleep` no caminho sync | Task 2 (preservado) |
| Testes async via `asyncio.run` | Task 1 |
| README com exemplo async | Task 3 |
| Sem mudanças em `anti_captcha` | Nenhuma task toca o arquivo |
| Sem `pytest-asyncio` | Task 1 usa `asyncio.run` |
