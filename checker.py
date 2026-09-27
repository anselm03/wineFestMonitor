"""
Modul zur inhaltlichen Auswertung der abgerufenen Seite.

Bestimmt anhand des rohen HTML, ob die Veranstaltung laut Website noch als
"complet" (ausgebucht) markiert ist oder nicht. Kennt nichts über HTTP,
Telegram oder Speicherung – reine Text-/HTML-Analyse.

Statuswerte (Domänenbegriffe konsequent auf Französisch, wie besprochen):
    STATUT_COMPLET     -> Reservierungsbereich zeigt weiterhin "complet".
    STATUT_DISPONIBLE  -> Reservierungsbereich existiert, zeigt aber etwas
                           ANDERES als "complet" (z. B. ein echtes Formular).
    STATUT_INCONNU      -> Der erwartete Reservierungsbereich (Überschrift
                           "Réservez votre participation") wurde gar nicht
                           gefunden -> Seite wurde vermutlich umgebaut,
                           die Prüfung ist damit nicht mehr verlässlich.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

STATUT_COMPLET = "complet"
STATUT_DISPONIBLE = "disponible"
STATUT_INCONNU = "inconnu"

# Anker-Überschrift, an der wir uns im Text orientieren, um den
# Reservierungsbereich zu finden (unabhängig von CSS-Klassen/IDs, die sich
# bei einem Website-Relaunch leicht ändern können).
_TEXTE_ANCRE = "reservez votre participation"
_MARQUEUR_COMPLET = "evenement est complet"

# Wie viele Zeichen nach dem Anker-Text wir uns anschauen, um den
# tatsächlichen Status zu finden bzw. als Kontext-Schnipsel mitzugeben.
_TAILLE_FENETRE = 1000
_TAILLE_EXTRAIT = 300


@dataclass
class ResultatVerification:
    """Ergebnis einer einzelnen Status-Prüfung."""

    statut: str
    extrait: str


def _normaliser(texte: str) -> str:
    """Kleinschreibung + Entfernen von Akzenten für robusten Textvergleich."""
    texte = texte.lower()
    texte = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in texte if not unicodedata.combining(c))


def determine_status(html: str) -> ResultatVerification:
    """Analysiert das HTML und liefert den erkannten Reservierungs-Status.

    Args:
        html: Der rohe HTML-Inhalt der Event-Seite.

    Returns:
        ResultatVerification mit Statuswert und einem kurzen Text-Auszug
        zur Nachvollziehbarkeit (u. a. für die Telegram-Nachricht/Logs).
    """
    soup = BeautifulSoup(html, "html.parser")
    texte_brut = soup.get_text(separator="\n")
    texte_normalise = _normaliser(texte_brut)

    index_ancre = texte_normalise.find(_TEXTE_ANCRE)
    if index_ancre == -1:
        logger.warning(
            "Anker-Text '%s' nicht im HTML gefunden – Seitenstruktur hat "
            "sich vermutlich geändert.",
            _TEXTE_ANCRE,
        )
        return ResultatVerification(statut=STATUT_INCONNU, extrait="")

    debut_fenetre = index_ancre
    fin_fenetre = index_ancre + _TAILLE_FENETRE
    fenetre_normalisee = texte_normalise[debut_fenetre:fin_fenetre]

    # Den unveränderten (nicht normalisierten) Text für den Extrakt
    # verwenden, damit die Telegram-Nachricht lesbar bleibt.
    extrait_lisible = " ".join(
        texte_brut[debut_fenetre:fin_fenetre].split()
    )[:_TAILLE_EXTRAIT]

    if _MARQUEUR_COMPLET in fenetre_normalisee:
        logger.info("Status erkannt: %s", STATUT_COMPLET)
        return ResultatVerification(statut=STATUT_COMPLET, extrait=extrait_lisible)

    logger.info(
        "Marker '%s' NICHT gefunden im Reservierungsbereich -> Status %s",
        _MARQUEUR_COMPLET,
        STATUT_DISPONIBLE,
    )
    return ResultatVerification(statut=STATUT_DISPONIBLE, extrait=extrait_lisible)
