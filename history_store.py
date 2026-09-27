"""
Modul zur Speicherung des Status-Verlaufs als JSON-Lines-Datei (JSONL).

Jede Zeile der Datei ist ein eigenständiges, valides JSON-Objekt. Neue
Einträge werden per Append (O(1), kein Neuschreiben der ganzen Datei)
hinzugefügt. Das macht die Datei robust gegen Abbrüche mitten im Lauf und
beliebig lang fortsetzbar, ohne dass man wie bei einem einzelnen großen
JSON-Array jedes Mal die komplette Datei neu parsen/schreiben müsste.

Kennt nichts über HTTP, Telegram oder HTML-Parsing – reine Persistenz.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_PATH = Path(__file__).resolve().parent / "data" / "historique_statuts.jsonl"


@dataclass
class EntreeHistorique:
    """Ein einzelner Eintrag im Status-Verlauf."""

    horodatage: str  # ISO-8601, inkl. Zeitzone
    statut: str
    extrait: str = ""
    details_erreur: Optional[str] = None


def append_entry(
    statut: str,
    extrait: str = "",
    details_erreur: Optional[str] = None,
    chemin: Path = DEFAULT_HISTORY_PATH,
) -> EntreeHistorique:
    """Hängt einen neuen Status-Eintrag mit aktuellem Zeitstempel an.

    Args:
        statut: Einer der STATUT_*-Werte aus checker.py.
        extrait: Optionaler Text-Auszug zur Nachvollziehbarkeit.
        details_erreur: Optionale Fehlerdetails (nur bei Abruf-Fehlern).
        chemin: Pfad zur JSONL-Datei (überschreibbar, v. a. für Tests).

    Returns:
        Die geschriebene EntreeHistorique.
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)

    entree = EntreeHistorique(
        horodatage=datetime.now(timezone.utc).astimezone().isoformat(),
        statut=statut,
        extrait=extrait,
        details_erreur=details_erreur,
    )

    with chemin.open("a", encoding="utf-8") as fichier:
        fichier.write(json.dumps(asdict(entree), ensure_ascii=False) + "\n")

    logger.debug("Neuer Historien-Eintrag geschrieben: %s", entree)
    return entree


def get_latest_entry(chemin: Path = DEFAULT_HISTORY_PATH) -> Optional[EntreeHistorique]:
    """Liest den zuletzt geschriebenen Eintrag aus der Historie.

    Effizient für sehr große Dateien: liest die Datei rückwärts in
    Blöcken statt sie komplett in den Speicher zu laden.

    Returns:
        Die letzte EntreeHistorique, oder None, falls die Datei noch
        nicht existiert oder leer ist.
    """
    if not chemin.exists():
        return None

    with chemin.open("rb") as fichier:
        fichier.seek(0, 2)  # ans Dateiende springen
        taille = fichier.tell()
        if taille == 0:
            return None

        taille_bloc = 4096
        position = taille
        tampon = b""

        while position > 0:
            lire = min(taille_bloc, position)
            position -= lire
            fichier.seek(position)
            tampon = fichier.read(lire) + tampon
            if tampon.count(b"\n") >= 2:
                break

        lignes = [ligne for ligne in tampon.split(b"\n") if ligne.strip()]
        if not lignes:
            return None

        derniere_ligne = lignes[-1].decode("utf-8")

    donnees = json.loads(derniere_ligne)
    return EntreeHistorique(**donnees)
