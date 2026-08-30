"""Configuración central de logging para todo el pipeline."""

import logging
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_logger(name: str, filename: str = "pipeline.log") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # ya configurado, evita handlers duplicados

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_DIR / filename, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
