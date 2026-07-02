"""utils_rpa - utilitários e configurações para facilitar o desenvolvimento de RPA com Python."""

from utils_rpa.logger import configure_logger
from utils_rpa.retry import retry_with_logging
from utils_rpa.screenshot import capture_screen

__version__ = "0.1.0"

__all__ = ["__version__", "configure_logger", "retry_with_logging", "capture_screen"]
