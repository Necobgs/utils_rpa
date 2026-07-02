"""Decorator de retentativa (retry) com logging integrado."""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
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

    Args:
        logger_name: Nome do logger usado para registrar as tentativas. Por
            padrão, o nome do módulo (``__name__``).
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
