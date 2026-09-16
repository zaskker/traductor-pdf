import logging
import sys
from logging.handlers import RotatingFileHandler
from src.application.runtime import get_logs_path

_logger_initialized = False


def setup_logger():
    global _logger_initialized
    logger = logging.getLogger("TraductorPDF")

    if not _logger_initialized:
        logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # File handler
        log_file = get_logs_path() / "app.log"
        try:
            fh = RotatingFileHandler(
                str(log_file), maxBytes=10 * 1024 * 1024, backupCount=3, encoding='utf-8'
            )
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except PermissionError:
            pass  # Likely a child process in a test environment where the parent locked the file

        _logger_initialized = True

    return logger


logger = setup_logger()
