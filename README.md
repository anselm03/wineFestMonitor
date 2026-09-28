# Montmartre-Vignes Reservierungs-Monitor

Prüft, ob auf der Seite

https://fetedesvendangesdemontmartre.com/evenement/les-visites-des-vignes/#form

im Reservierungsbereich weiterhin **„Cet événement est complet“** steht,
und schickt eine Telegram-Nachricht, sobald dort etwas anderes steht
(z. B. ein echtes Reservierungsformular).

## Lokales Setup (für manuelle Testläufe)

```bash
pip install -r requirements.txt
cp .env.example .env
# .env öffnen und TELEGRAM_BOT_TOKEN sowie TELEGRAM_CHAT_ID eintragen
```

`curl` muss zusätzlich als Kommandozeilenprogramm verfügbar sein (ist auf
den meisten Linux-Systemen vorinstalliert) – es dient als einer der
Fallbacks in der Abruf-Kette.

```bash
python main.py
```

## Betrieb über GitHub Actions (empfohlen, kein eigener Server nötig)

Der Workflow unter `.github/workflows/monitor.yml` führt `main.py`
automatisch nach einem Zeitplan aus – kostenlos, ganz ohne dass ein
eigener Rechner/Server dafür laufen muss.

### Einmalige Einrichtung

1. **Repository auf GitHub anlegen** und den kompletten Ordnerinhalt
   hineinpushen (inkl. `.github/`-Ordner, aber **ohne** eine echte
   `.env`-Datei – die ist über `.gitignore` bereits ausgeschlossen).
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<dein-user>/<dein-repo>.git
   git push -u origin main
   ```
2. **Sichtbarkeit des Repos wählen** (Public vs. Private) – siehe
   Abwägung unten.
3. **Secrets hinterlegen**: im Repo unter *Settings → Secrets and
   variables → Actions → New repository secret* zwei Einträge anlegen:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   Diese werden dem Workflow als Umgebungsvariablen übergeben, genau wie
   lokal die `.env` – der Code selbst muss dafür nicht angepasst werden.
4. **Schreibrechte für den Workflow aktivieren**: unter *Settings →
   Actions → General → Workflow permissions* die Option **„Read and
   write permissions“** auswählen und speichern. Ohne das darf der
   Workflow die aktualisierte Status-Historie nicht zurück ins Repo
   committen (siehe unten).
5. **Testen**: im Reiter *Actions* den Workflow „Montmartre-Vignes
   Reservierungs-Monitor“ auswählen und über *„Run workflow“* manuell
   einmal auslösen. Im Log des Laufs siehst du dieselbe Ausgabe wie
   lokal (dank identischem `logging_config.py` mit Konsolen-Handler).

Danach läuft der Workflow automatisch nach dem in `monitor.yml`
hinterlegten Zeitplan (aktuell alle 10 Minuten, versetzt auf
`:03/:13/:23/:33/:43/:53`) – ganz ohne dass dein PC oder Home-Server an
sein muss.

### Public vs. Private Repository

| | Public | Private |
|---|---|---|
| Actions-Minuten | unbegrenzt, kostenlos | 2.000 Freiminuten/Monat |
| Sichtbarkeit | Code (ohne Secrets!) für jeden einsehbar | nur für dich sichtbar |
| Reicht für 10-Minuten-Takt? | ja, problemlos | ja, mit `pip`-Cache i. d. R. auch – bei kürzerem Takt (z. B. alle 5 Min.) ggf. knapp |

Die Telegram-Zugangsdaten liegen in **jedem Fall** nur als verschlüsseltes
GitHub Secret vor, nie im Code – ein öffentliches Repo gibt also nur den
Quellcode preis, keine Geheimnisse.

### Warum der Workflow die History zurück-committet

GitHub-Actions-Runner sind bei jedem Lauf eine frische, leere virtuelle
Maschine – nichts bleibt automatisch zwischen zwei Läufen erhalten. Die
Programmlogik selbst braucht das nicht (ein Eintrag wird geschrieben und
im selben Lauf sofort wieder gelesen), aber damit `data/historique_statuts.jsonl`
über die Zeit als durchgängiger Verlauf erhalten bleibt, committet der
letzte Schritt im Workflow die Datei automatisch zurück ins Repo, falls
sie sich geändert hat.

### [unsure] Timing-Realität bei Scheduled Workflows

GitHub liefert `schedule`-Events nur „best effort“, ohne Pünktlichkeits-
garantie – bei hoher Auslastung der Actions-Infrastruktur können Läufe
sich um mehrere Minuten, teils über eine Stunde verzögern, gelegentlich
fallen einzelne Läufe auch ganz aus. Für ein zeitkritisches Monitoring
wie dieses (Plätze könnten sehr schnell weg sein) war das ein reales,
nicht wegzudiskutierendes Risiko. Deshalb wurde der interne
`schedule`-Trigger entfernt und durch einen externen Trigger ersetzt –
siehe nächster Abschnitt.

## Telegram-Versand isoliert testen

Ein regulärer Lauf schickt bei „complet“ bewusst keine Nachricht. Um
Bot-Token und Chat-ID trotzdem zu prüfen, gibt es einen Testmodus, der
Seitenabruf, Statusprüfung und History überspringt und nur eine
Testnachricht sendet:

- **Auf GitHub:** Actions-Tab → Workflow auswählen → **Run workflow** →
  Häkchen bei „Nur Telegram-Testnachricht senden“ setzen → starten.
- **Lokal:** `MONTMARTRE_TEST_NOTIFICATION=1 python main.py` (benötigt
  eine lokale `.env` mit echten Zugangsdaten).

Kommt die Nachricht an, funktioniert der Versand. Kommt sie nicht an,
steht der Grund im Log des Laufs (z. B. fehlende Secrets oder eine
falsche Chat-ID). Beim externen Aufruf über cron-job.org ist der Schalter
nicht gesetzt, dort läuft also immer die normale Prüfung.

## Externer Trigger via cron-job.org (statt GitHub's eigenem Scheduler)

Der Workflow wird jetzt nicht mehr von GitHub selbst nach Zeitplan
gestartet, sondern von außen: der kostenlose Dienst
[cron-job.org](https://cron-job.org) ruft in festen Abständen einen
GitHub-API-Endpunkt auf, der den Workflow per `workflow_dispatch`
auslöst. Das ist in der Praxis deutlich pünktlicher, weil ein einzelner,
leichtgewichtiger HTTP-Call nicht durch GitHub's eigene, teils
überlastete Scheduling-Warteschlange muss.

### 1. Fine-grained Personal Access Token (PAT) bei GitHub erzeugen

GitHub → Profilbild → **Settings** → ganz unten links **Developer
settings** → **Personal access tokens** → **Fine-grained tokens** →
**Generate new token**.

- **Token name:** z. B. `cron-job-org-montmartre-monitor`
- **Expiration:** z. B. 90 Tage (kürzer = sicherer, du musst ihn dann
  aber regelmäßig erneuern)
- **Repository access:** **Only select repositories** → dein
  Montmartre-Monitor-Repo auswählen (NICHT „All repositories“)
- **Permissions → Repository permissions → Actions:** auf
  **Read and write** stellen (das ist die einzige Berechtigung, die
  für das Auslösen des Workflows gebraucht wird)
- Token generieren und den angezeigten Wert (beginnt mit `github_pat_…`)
  **sofort kopieren** – er wird danach nie wieder angezeigt.

### 2. Bei cron-job.org einen Job einrichten

Kostenloser Account auf [cron-job.org](https://cron-job.org) (eigener
Account, unabhängig von GitHub). Dann **„Create cronjob“**:

- **Title:** z. B. `Montmartre Monitor Trigger`
- **URL:**
  ```
  https://api.github.com/repos/<dein-github-user>/<dein-repo-name>/actions/workflows/monitor.yml/dispatches
  ```
- **Request method:** `POST`
- **Common → Save responses:** ruhig aktivieren, hilft beim Debuggen
- **Headers** (bei „Advanced“ bzw. im Job-Editor unter „Headers“):
  | Name | Wert |
  |---|---|
  | `Authorization` | `Bearer <dein-PAT-hier-einfügen>` |
  | `Accept` | `application/vnd.github+json` |
  | `Content-Type` | `application/json` |
  | `X-GitHub-Api-Version` | `2022-11-28` |
- **Request body:**
  ```json
  {"ref": "main"}
  ```
  (`main` durch den Namen deines Default-Branch ersetzen, falls der
  anders heißt)
- **Schedule:** z. B. „every 10 minutes“ (cron-job.org erlaubt bis zu
  1-Minuten-Takt, kostenlos, unbegrenzt viele Jobs)

Über den **„Test run“**-Button im Job-Editor kannst du sofort prüfen, ob
der Aufruf funktioniert, ohne auf den nächsten Zeitplan-Tick zu warten –
bei Erfolg antwortet die GitHub-API mit Status **204 No Content**, und
im Actions-Tab deines Repos sollte fast augenblicklich ein neuer,
manuell wirkender Lauf auftauchen.

### Sicherheitsrahmen des Tokens

- Der Token ist **kein GitHub-Passwort** – ein separat erzeugter,
  jederzeit einzeln widerrufbarer Schlüssel.
- Er wirkt **nur auf das eine ausgewählte Repository**, nicht auf deinen
  gesamten Account.
- Er kann **ausschließlich** Actions auslösen/verwalten – nichts an
  Code, Issues, Einstellungen usw.
- Läuft automatisch nach der gewählten Frist ab; du kannst ihn jederzeit
  vorzeitig unter GitHub → Settings → Developer settings → Personal
  access tokens widerrufen.
- Er liegt ausschließlich bei cron-job.org als Header-Wert deines Jobs –
  nirgends im Code oder Repo.

## Alternative: lokal per Cron (eigener Rechner/Server)

Falls du das Skript doch auf einer eigenen, dauerhaft laufenden Maschine
betreiben willst:

```cron
*/5 * * * * cd /pfad/zum/projekt && /pfad/zum/venv/bin/python main.py >> logs/cron.log 2>&1
```

Wichtig: Der Cron-Job muss im Projektverzeichnis laufen (oder `cd` davor),
damit `.env`, `data/` und `logs/` relativ gefunden werden.

## Architektur

| Modul               | Verantwortung                                                        |
|---------------------|------------------------------------------------------------------------|
| `fetcher.py`        | HTTP-Abruf der Seite mit Fallback-Kette (`requests` → `httpx` → `curl` → `urllib`) |
| `checker.py`        | Bestimmt den Status (`complet` / `disponible` / `inconnu`) aus dem HTML |
| `history_store.py`  | Schreibt/liest den Status-Verlauf als JSONL-Datei (`data/historique_statuts.jsonl`) |
| `notifier.py`       | Versand von Telegram-Nachrichten, liest Zugangsdaten aus `.env`         |
| `logging_config.py` | Zentrale `dictConfig`-Logging-Konfiguration (Konsole + rotierende Datei) |
| `main.py`            | Orchestriert einen einzelnen Prüflauf (kein eigenes Scheduling)        |
| `.github/workflows/monitor.yml` | Scheduling über GitHub Actions statt lokalem Cron-Job       |

Jedes Modul kennt nur seine eigene Zuständigkeit (Kapselung): der Fetcher
weiß nichts über HTML-Inhalte, der Checker nichts über HTTP oder Telegram,
der Notifier nichts über HTML-Parsing usw. `main.py` verdrahtet die
Module miteinander.

## Status-Logik

- **`complet`**: Reservierungsbereich gefunden, Text „…événement est
  complet“ steht weiterhin da → **keine** Nachricht.
- **`disponible`**: Reservierungsbereich gefunden, aber der
  „complet“-Marker fehlt → **bei jedem Lauf** eine Telegram-Nachricht
  (bewusst ohne Deduplizierung, da zeitkritisch).
- **`inconnu`**: Weder die Überschrift „Réservez votre participation“
  noch etwas Auswertbares gefunden → Seite hat sich vermutlich
  strukturell verändert → Warn-Nachricht, manuell prüfen.
- **Abruf-Fehler** (alle HTTP-Methoden fehlgeschlagen): eigener
  `inconnu`-Eintrag mit Fehlerdetails + sofortige Telegram-Nachricht mit
  den gesammelten Fehlermeldungen aller Methoden.

## Bekannte Unsicherheiten [unsure]

- [unsure] Ich konnte die Zielseite nicht aus meiner eigenen
  Sandbox-Umgebung abrufen (Netzwerk-Whitelist erlaubt diese Domain
  nicht) und habe daher nur den von meinem `web_fetch`-Tool
  bereitgestellten, bereits zu Markdown konvertierten Inhalt gesehen,
  nicht das rohe HTML mit echten Tag-/Klassennamen. Der Checker orientiert
  sich deshalb bewusst nicht an CSS-Klassen/IDs, sondern rein am
  sichtbaren Text („Réservez votre participation“ als Anker, „…événement
  est complet“ als Marker) – das sollte robuster gegen Layout-Änderungen
  sein, aber teste den ersten echten Lauf trotzdem genau (Log + JSONL
  prüfen), bevor du dich voll darauf verlässt.
- [unsure] Ich weiß nicht, wie die Seite aussieht, wenn tatsächlich
  Plätze frei sind (z. B. ob dann ein anderes Icon statt 🔴 erscheint,
  etwa 🟢, und/oder ein echtes Formular eingeblendet wird). Die Logik
  behandelt „alles außer complet“ als potenziellen Alarm, das sollte
  also in jedem Fall greifen.
- [unsure] Manche Websites blockieren automatisierte Requests (Bot-
  Schutz, Cloudflare o. Ä.) unabhängig von der HTTP-Bibliothek. Die
  Fallback-Kette hilft bei clientseitigen Unterschieden (TLS-Fingerprint
  etc.), aber falls ALLE vier Methoden dauerhaft blockiert werden, hilft
  nur eine grundsätzlich andere Lösung (z. B. Headless-Browser) – das
  merkst du an wiederholten Fehler-Telegram-Nachrichten mit gleichem
  Muster.
