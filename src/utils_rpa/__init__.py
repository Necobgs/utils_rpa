"""utils_rpa - utilitários e configurações para facilitar o desenvolvimento de RPA com Python."""

from utils_rpa.forms import extract_inputs
from utils_rpa.logger import (
    cleanup_logs_by_last_update,
    cleanup_old_logs,
    configure_logger,
    configure_logger_by_id,
)
from utils_rpa.retry import retry_with_logging
from utils_rpa.screenshot import capture_screen

__version__ = "0.2.3"

__all__ = [
    "__version__",
    "configure_logger",
    "configure_logger_by_id",
    "cleanup_old_logs",
    "cleanup_logs_by_last_update",
    "retry_with_logging",
    "capture_screen",
    "extract_inputs",
]
