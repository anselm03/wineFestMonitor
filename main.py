"""
Einstiegspunkt für einen einzelnen Prüflauf.

Dieses Skript führt KEIN eigenes Scheduling durch – das übernimmt ein
externer Cron-Job, der ``python main.py`` in regelmäßigen Abständen
aufruft. Ein einzelner Lauf macht genau Folgendes:

    1. Seite abrufen (fetcher.py, mit Fallback-Kette).
       -> Bei Fehlschlag: Fehler-Eintrag in die History schreiben und
          SOFORT eine Telegram-Nachricht mit den Fehlerdetails senden.
    2. Status aus dem HTML bestimmen (checker.py).
    3. Status-Eintrag in die History anhängen (history_store.py).
    4. Den zuletzt geschriebenen History-Eintrag auswerten und je nach
       Status ggf. eine Telegram-Nachricht senden (notifier.py):
           - STATUT_DISPONIBLE / STATUT_INCONNU -> Nachricht wird gesendet
             (zeitkritisch: bewusst bei JEDEM Lauf, keine Deduplizierung).
           - STATUT_COMPLET -> keine Nachricht.

Zusätzlich gibt es ganz außen ein "Notfall-Netz": Sollte irgendetwas
komplett Unerwartetes passieren (Programmierfehler, kaputte Abhängigkeit
usw.), das NICHT bereits von einem der obigen Schritte behandelt wird,
fängt ``main()`` das ab, loggt den vollständigen Traceback und schickt
trotzdem noch eine Telegram-Notfall-Nachricht ("Hand, die sich aus dem
Wasser streckt") – damit ein Totalausfall nicht lautlos im Cron-Log
verschwindet, sondern du aktiv benachrichtigt wirst.
Zusätzlich gibt es einen Test-Modus, der die komplette Prüflogik
überspringt und nur eine Testnachricht sendet (Umgebungsvariable
``MONTMARTRE_TEST_NOTIFICATION=1`` bzw. der entsprechende Input beim
manuellen "Run workflow" auf GitHub) – so lässt sich der Telegram-Versand
isoliert testen, unabhängig vom aktuellen Reservierungsstatus der Seite.
"""

from __future__ import annotations

import logging
import os
import sys
import traceback

from checker import STATUT_COMPLET, STATUT_DISPONIBLE, STATUT_INCONNU, determine_status
from fetcher import FetchError, fetch_page
from history_store import append_entry, get_latest_entry
from logging_config import configure_logging
from notifier import send_telegram_message

URL_CIBLE = (
    "https://fetedesvendangesdemontmartre.com/evenement/les-visites-des-vignes/#form"
)

# Umgebungsvariable, um NUR eine Telegram-Testnachricht zu senden, ohne
# die Seite abzurufen oder die History zu beschreiben. Praktisch, um den
# Telegram-Versand isoliert zu testen, unabhängig vom aktuellen Status
# der Zielseite (z. B. wenn diese gerade "complet" zeigt und ein
# regulärer Lauf deshalb ohnehin keine Nachricht senden würde).
ENV_VAR_TEST_NOTIFICATION = "MONTMARTRE_TEST_NOTIFICATION"
_WERTE_WAHR = {"1", "true", "yes", "on"}

logger = logging.getLogger(__name__)


def _gerer_erreur_abrup(erreur: FetchError) -> None:
    """Behandelt einen vollständigen Fetch-Fehlschlag: History + Alarm."""
    logger.error("Abruf endgültig fehlgeschlagen: %s", erreur)

    append_entry(statut=STATUT_INCONNU, details_erreur=str(erreur))

    message = (
        "⚠️ Fehler beim Prüfen der Reservierungsseite (Vignes du Clos "
        "Montmartre).\n\n"
        f"Alle Abrufmethoden sind fehlgeschlagen:\n{erreur}\n\n"
        "Das Monitoring ist gerade blind, bitte manuell prüfen: "
        f"{URL_CIBLE}"
    )
    send_telegram_message(message)


def _notifier_selon_statut(statut: str, extrait: str) -> None:
    """Sendet ggf. eine Telegram-Nachricht basierend auf dem Status."""
    if statut == STATUT_COMPLET:
        logger.info("Event weiterhin komplett ausgebucht – keine Benachrichtigung.")
        return

    if statut == STATUT_DISPONIBLE:
        message = (
            "🎉 Möglicherweise sind Plätze frei geworden bei "
            "'Les Visites des vignes'!\n\n"
            f"Gefundener Text: \u201e{extrait}\u201c\n\n"
            f"Jetzt reservieren: {URL_CIBLE}"
        )
        logger.warning("Status weicht von 'complet' ab -> sende Alarm-Nachricht.")
        send_telegram_message(message)
        return

    if statut == STATUT_INCONNU:
        message = (
            "⚠️ Der erwartete Reservierungsbereich wurde auf der Seite "
            "nicht gefunden. Die Seitenstruktur hat sich vermutlich "
            "geändert – bitte manuell prüfen, die automatische Erkennung "
            f"ist aktuell unzuverlässig: {URL_CIBLE}"
        )
        logger.warning("Anker-Text nicht gefunden -> sende Warn-Nachricht.")
        send_telegram_message(message)
        return

    # Sollte nie erreicht werden, außer bei zukünftig neu eingeführten
    # Statuswerten, die hier noch nicht behandelt wurden.
    logger.error("Unbekannter Statuswert '%s' – keine Aktion definiert.", statut)


def _gerer_crash_complet(exc: BaseException) -> None:
    """Letztes Sicherheitsnetz bei einem komplett unerwarteten Absturz.

    Wird NUR erreicht, wenn ein Fehler auftritt, der von keinem der
    regulären Pfade (FetchError etc.) abgefangen wurde – also z. B. ein
    Bug in diesem Code selbst. Loggt den vollständigen Traceback und
    versucht trotzdem, per Telegram ein Notfall-Signal zu senden. Der
    Telegram-Versand selbst ist dabei nochmal einzeln abgesichert, damit
    ein Fehler IM Notfall-Versand nicht den Crash-Handler selbst zum
    Absturz bringt.
    """
    traceback_texte = traceback.format_exc()
    logger.critical("Unerwarteter Totalausfall des Skripts:\n%s", traceback_texte)

    # Traceback für Telegram einkürzen (Nachrichtenlänge begrenzt).
    traceback_gekuerzt = traceback_texte[-2500:]

    message = (
        "🆘🤚 Notfall-Signal vom Montmartre-Monitor!\n\n"
        "Das Skript ist mit einem unerwarteten Fehler abgestürzt, den "
        "die reguläre Fehlerbehandlung nicht aufgefangen hat. Das "
        "Monitoring steht vermutlich still, bis das behoben ist.\n\n"
        f"Fehlertyp: {type(exc).__name__}: {exc}\n\n"
        f"Traceback (ggf. gekürzt):\n{traceback_gekuerzt}"
    )

    try:
        send_telegram_message(message)
    except Exception:  # pragma: no cover - absolute Notbremse
        logger.critical(
            "Auch der Versand der Notfall-Telegram-Nachricht ist "
            "fehlgeschlagen:\n%s",
            traceback.format_exc(),
        )


def _executer_prufung() -> int:
    """Führt den eigentlichen, regulären Prüflauf durch."""
    logger.info("Prüflauf gestartet.")

    try:
        html = fetch_page(URL_CIBLE)
    except FetchError as erreur:
        _gerer_erreur_abrup(erreur)
        return 1

    resultat = determine_status(html)
    append_entry(statut=resultat.statut, extrait=resultat.extrait)

    entree_courante = get_latest_entry()
    if entree_courante is None:  # pragma: no cover - sollte nie passieren
        logger.error("Konnte den soeben geschriebenen History-Eintrag nicht lesen.")
        return 1

    _notifier_selon_statut(entree_courante.statut, entree_courante.extrait)

    logger.info("Prüflauf beendet.")
    return 0


def _test_modus_aktiv() -> bool:
    """Prüft, ob der reine Telegram-Testmodus angefordert wurde."""
    return os.environ.get(ENV_VAR_TEST_NOTIFICATION, "").strip().lower() in _WERTE_WAHR


def _executer_test_notification() -> int:
    """Sendet ausschließlich eine Telegram-Testnachricht.

    Überspringt Abruf, Statusprüfung und History komplett, damit der
    Telegram-Versand isoliert und unabhängig vom aktuellen Zustand der
    Zielseite getestet werden kann.

    Returns:
        0, wenn die Nachricht versendet wurde, sonst 1.
    """
    logger.info("Test-Modus aktiv: sende nur eine Telegram-Testnachricht.")
    message = (
        "✅ Testnachricht vom Montmartre-Monitor.\n\n"
        "Wenn du das liest, funktionieren Bot-Token und Chat-ID. "
        "Es wurde keine Seitenprüfung durchgeführt."
    )
    if send_telegram_message(message):
        return 0
    logger.error("Testnachricht konnte nicht gesendet werden (Details siehe oben).")
    return 1


def main() -> int:
    try:
        configure_logging()
    except Exception:
        # Selbst wenn das Logging-Setup fehlschlägt, soll das Skript
        # nicht stillschweigend nichts tun -> wenigstens auf stderr
        # ausgeben (landet dank ">> logs/cron.log 2>&1" trotzdem in
        # einer Datei) und danach weiter versuchen, per Telegram zu
        # alarmieren.
        print(
            "KRITISCH: Logging-Konfiguration fehlgeschlagen:\n"
            + traceback.format_exc(),
            file=sys.stderr,
        )

    try:
        if _test_modus_aktiv():
            return _executer_test_notification()
        return _executer_prufung()
    except Exception as exc:  # bewusst breit: allerletztes Sicherheitsnetz
        _gerer_crash_complet(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
