"""
Zentrale Logging-Konfiguration.

Es gibt genau einen Root-Handler-Satz (Konsole + rotierende Datei), aber
jedes Modul holt sich über ``logging.getLogger(__name__)`` seinen eigenen
Logger, sodass im Log ersichtlich ist, aus welcher Datei ein Eintrag stammt.
Konfiguriert wird ausschließlich über ``logging.config.dictConfig``.
"""

from __future__ import annotations

import logging.config
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "montmartre_monitor.log"


def configure_logging(niveau: str = "INFO") -> None:
    """Initialisiert das Logging für den gesamten Lauf des Skripts.

    Args:
        niveau: Log-Level als String (z. B. "DEBUG", "INFO", "WARNING").
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": niveau,
                "formatter": "standard",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "standard",
                "filename": str(LOG_FILE),
                "maxBytes": 1_000_000,
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "root": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
        },
    }

    logging.config.dictConfig(config)
