"""
Modul zum Versand von Telegram-Nachrichten.

Liest Bot-Token und Chat-ID ausschließlich aus Umgebungsvariablen
(``TELEGRAM_BOT_TOKEN`` / ``TELEGRAM_CHAT_ID``), die typischerweise über
eine lokale ``.env``-Datei (via python-dotenv) gesetzt werden. Kennt
nichts über HTML-Parsing oder die History-Datei – reine
Benachrichtigungslogik.
"""

from __future__ import annotations

import logging
import os

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
DEFAULT_TIMEOUT_SECONDS = 15


class ConfigurationTelegramManquante(Exception):
    """Wird geworfen, wenn Token und/oder Chat-ID nicht gesetzt sind."""


def _charger_configuration() -> tuple[str, str]:
    """Lädt .env (falls vorhanden) und liest die benötigten Variablen.

    Raises:
        ConfigurationTelegramManquante: wenn Token oder Chat-ID fehlen.
    """
    load_dotenv()  # no-op, falls keine .env existiert

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    variables_manquantes = [
        nom
        for nom, valeur in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id))
        if not valeur
    ]
    if variables_manquantes:
        raise ConfigurationTelegramManquante(
            "Fehlende Umgebungsvariable(n): " + ", ".join(variables_manquantes)
        )

    # mypy/type-checker beruhigen: an dieser Stelle sind beide gesetzt.
    assert token is not None and chat_id is not None
    return token, chat_id


def send_telegram_message(texte: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> bool:
    """Sendet eine Textnachricht per Telegram-Bot-API.

    Args:
        texte: Der zu sendende Nachrichtentext.
        timeout: Timeout in Sekunden für den HTTP-Request.

    Returns:
        True bei Erfolg, False bei jedem Fehlschlag (wird geloggt, aber
        bewusst nicht weitergeworfen – ein fehlgeschlagener Alarm-Versand
        soll den Rest des Programmlaufs nicht zum Absturz bringen).
    """
    try:
        token, chat_id = _charger_configuration()
    except ConfigurationTelegramManquante as exc:
        logger.error("Telegram-Konfiguration unvollständig: %s", exc)
        return False

    url = TELEGRAM_API_URL.format(token=token)
    try:
        reponse = requests.post(
            url,
            json={"chat_id": chat_id, "text": texte},
            timeout=timeout,
        )
        reponse.raise_for_status()
    except Exception as exc:  # bewusst breit: Netzwerk-/API-Fehler aller Art
        logger.error("Versand der Telegram-Nachricht fehlgeschlagen: %s", exc)
        return False

    logger.info("Telegram-Nachricht erfolgreich versendet.")
    return True
