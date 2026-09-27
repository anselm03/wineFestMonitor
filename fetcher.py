"""
Modul zum Abruf der HTML-Seite.

Kapselt ausschließlich das "Wie komme ich an den HTML-Inhalt der Seite".
Es kennt weder die Zielseite inhaltlich (kein Parsing), noch weiß es etwas
über Telegram oder die History. Es probiert der Reihe nach mehrere
unabhängige Methoden, einen HTTP-Request abzusetzen, und nimmt die erste,
die funktioniert. Schlagen alle fehl, wird eine ``FetchError`` mit allen
gesammelten Teilfehlern geworfen.

[unsure] Ich kann die tatsächliche Erreichbarkeit/Blockade der Zielseite
(z. B. durch Cloudflare, Bot-Schutz o. Ä.) von hier aus nicht testen, da
meine Sandbox-Umgebung keinen Netzwerkzugriff auf diese Domain hat. Die
Fallback-Kette ist deshalb bewusst so gebaut, dass sie sich zur Laufzeit
bei dir selbst "durchtestet" und dabei jeden Fehlschlag loggt.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT_SECONDS = 20


@dataclass
class TentativeEchouee:
    """Protokolliert den Fehlschlag einer einzelnen Abrufmethode."""

    methode: str
    erreur: str


@dataclass
class FetchError(Exception):
    """Wird geworfen, wenn ALLE Abrufmethoden fehlgeschlagen sind."""

    url: str
    tentatives: list[TentativeEchouee] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - reine Darstellung
        details = "; ".join(f"{t.methode}: {t.erreur}" for t in self.tentatives)
        return f"Alle Abrufmethoden für {self.url} sind fehlgeschlagen ({details})"


def _essayer_requests(url: str, timeout: int) -> str:
    import requests  # lokal importiert, da optionale Abhängigkeit

    reponse = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": DEFAULT_USER_AGENT},
    )
    reponse.raise_for_status()
    return reponse.text


def _essayer_httpx(url: str, timeout: int) -> str:
    import httpx  # lokal importiert, da optionale Abhängigkeit

    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        reponse = client.get(url, headers={"User-Agent": DEFAULT_USER_AGENT})
        reponse.raise_for_status()
        return reponse.text


def _essayer_curl(url: str, timeout: int) -> str:
    resultat = subprocess.run(
        [
            "curl",
            "--silent",
            "--show-error",
            "--fail",
            "--location",
            "--max-time",
            str(timeout),
            "--user-agent",
            DEFAULT_USER_AGENT,
            url,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return resultat.stdout


def _essayer_urllib(url: str, timeout: int) -> str:
    import urllib.request

    requete = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(requete, timeout=timeout) as reponse:  # nosec B310
        charset = reponse.headers.get_content_charset() or "utf-8"
        return reponse.read().decode(charset, errors="replace")


# Reihenfolge der Fallback-Kette. [unsure] Die "beste" Reihenfolge hängt
# davon ab, ob die Zielseite z. B. auf das TLS-Fingerprinting von requests
# empfindlich reagiert (Stichwort Bot-Schutz) – falls requests dauerhaft
# blockiert wird, curl (nutzt eine andere TLS-Stack-Signatur) oder httpx
# probieren.
_METHODES = (
    ("requests", _essayer_requests),
    ("httpx", _essayer_httpx),
    ("curl", _essayer_curl),
    ("urllib", _essayer_urllib),
)


def fetch_page(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Ruft die übergebene URL ab und gibt den rohen HTML-Inhalt zurück.

    Probiert nacheinander mehrere unabhängige HTTP-Mechanismen durch.
    Sobald einer erfolgreich ist, wird dessen Ergebnis zurückgegeben und
    die restlichen Methoden werden nicht mehr versucht.

    Raises:
        FetchError: wenn ausnahmslos jede Methode fehlgeschlagen ist.
    """
    tentatives: list[TentativeEchouee] = []

    for nom_methode, fonction in _METHODES:
        try:
            logger.info("Versuche Abruf von %s via %s ...", url, nom_methode)
            contenu = fonction(url, timeout)
            logger.info(
                "Abruf via %s erfolgreich (%d Zeichen empfangen).",
                nom_methode,
                len(contenu),
            )
            return contenu
        except ModuleNotFoundError as exc:
            logger.warning(
                "Methode %s übersprungen, Abhängigkeit fehlt: %s", nom_methode, exc
            )
            tentatives.append(TentativeEchouee(nom_methode, f"Abhängigkeit fehlt: {exc}"))
        except Exception as exc:  # bewusst breit: jede Methode kann anders fehlschlagen
            logger.warning("Methode %s fehlgeschlagen: %s", nom_methode, exc)
            tentatives.append(TentativeEchouee(nom_methode, str(exc)))

    logger.error(
        "Sämtliche %d Abrufmethoden für %s sind fehlgeschlagen.",
        len(_METHODES),
        url,
    )
    raise FetchError(url=url, tentatives=tentatives)
