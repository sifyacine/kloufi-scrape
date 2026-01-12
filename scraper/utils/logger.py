import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")

    file_handler = RotatingFileHandler(LOG_DIR / "scraper.log", maxBytes=5_000_000, backupCount=5)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger