# BatteryWatch auf dem Kursserver

Was am Ende läuft (alles als Docker-Container unserer Gruppe, Ports 20800–20899):

```
Live-Broker mqtt.ti-labs.ai:8883 ──▶ Collector ──▶ unsere PostgreSQL (Port 20832)
Kurs-Datenbank (127.0.0.1:5432) ──einmaliger Import──▶ ┘           │
                                                           API ◀──┘
                                         Browser ──▶ Frontend (Port 20800)
```

- **Unsere Datenbank** ist neu und gehört nur uns. Die Kurs-Datenbank wird nur gelesen.
- Die Zugangsdaten stehen nur in `.env` auf dem Server (nicht in Git) – `tinf25d-llv.yaml` nie committen.

## So kommt eine neue Version auf den Server (wie in der Skizze vom Professor)

```
 (1) push auf main         (2) GitHub-Runner                 (3) Server, alle 5 Minuten
 ─────────────────▶  Tests (ci.yml) ─▶ Images bauen ─▶  ghcr.io  ◀── docker compose pull
                     .github/workflows/deploy.yml     (Registry)     docker compose up -d
                                                                     (systemd-Timer)
```

| Schritt | Datei | Was passiert |
|---|---|---|
| 1 | `.github/workflows/deploy.yml` | Nach erfolgreichen Tests auf `main` baut GitHub die Images `batterywatch-backend` und `batterywatch-frontend` und lädt sie nach **ghcr.io** (GitHub Container Registry) hoch – Tag `latest` und die Commit-Nummer. |
| 2 | `docker-compose.server.yml` | Wie `docker-compose.yml`, aber mit den **fertigen Images** von ghcr.io statt selbst bauen; ohne Test-Broker und Fake-Nodes. Auf dem Server steht in `.env` `COMPOSE_FILE=docker-compose.server.yml`, damit jedes `docker compose` diese Datei nimmt. |
| 3 | `deploy/batterywatch-update.service` + `.timer` | systemd führt alle 5 Minuten `git pull`, `docker compose pull` und `docker compose up -d` aus. Nur Container mit neuem Image werden neu gestartet; die Daten bleiben. |

Ein Push auf `main` ist damit nach etwa 5–10 Minuten live – ohne dass jemand den Server anfasst.
Variante (1) der Skizze: Der Server **fragt selbst nach** (kein offener Port, kein Server-Passwort bei GitHub).

**Zugriff auf die Images („deploy-token [RO]“):** Neue Pakete auf ghcr.io sind zunächst privat.
Entweder einmal auf GitHub öffentlich schalten (Repo-Seite → *Packages* → Paket → *Package settings* →
*Change visibility* → *Public*; das Repo ist ohnehin öffentlich, in den Images stehen keine Passwörter)
oder dem Server einen **Nur-Lese-Token** geben: GitHub → *Settings* → *Developer settings* →
*Personal access tokens (classic)* → nur `read:packages`. `setup-server.sh` fragt danach, falls nötig.

## 1. Einrichten (einmalig)

Voraussetzung: Der Branch ist in `main` gemergt und der Workflow **Deploy** ist auf GitHub
unter *Actions* einmal grün durchgelaufen (dann gibt es die Images auf ghcr.io).

```bash
ssh tinf25d-llv@212.227.31.76
git clone https://github.com/Totoba246/Software_Engineering_Semesterprojekt.git batterywatch
cd batterywatch
./deploy/setup-server.sh
```

Das Skript fragt nach dem **MQTT-Passwort** (Enter übernimmt die Vorgaben in `[...]`), erzeugt ein
eigenes Passwort für unsere Datenbank, schreibt alles in `.env`, lädt die Images, startet die
Container, legt den **ersten Admin** für die Webseite an (fragt nach Name und Passwort) und richtet
den systemd-Timer für die automatischen Updates ein. Alle weiteren Konten legt der Admin auf der
Webseite an (Nutzerverwaltung). **Keine Demo-Konten auf dem Server** – deren Passwort steht im Code.

Passwort eines Kontos auf dem Server zurücksetzen (z. B. Admin vergessen):

```bash
docker compose exec api python -m batterywatch.tools.manage reset-password admin
```

Prüfen, ob der Timer läuft:

```bash
systemctl --user list-timers                          # wann das nächste Update läuft
journalctl --user -u batterywatch-update.service      # was bei den Updates passiert ist
```

## 2. Historische Daten übernehmen

```bash
./deploy/import-history.sh --inspect   # zeigt nur, welche Tabellen/Spalten es gibt
./deploy/import-history.sh --check     # Plausibilitätsprüfung, importiert NICHTS
./deploy/import-history.sh             # übernimmt die Daten
./deploy/import-history.sh --to 2026-03-29T00:16:57+00:00   # nur bis zu diesem Zeitpunkt
```

`--check` zeigt je Gerät eine Tabelle pro Tag (Anzahl Werte, Anteil plausibel, Spannung
min/typisch/max, Strom), erkannte Akkuwechsel/Entladezyklen, Lücken, „hängende“ Werte und
**ab wann keine plausiblen Messwerte mehr kommen** – inklusive eines Vorschlags für `--to`.
Plausibel = 9–15 V und 0–5 A. Werte ≤ 0 V oder > 60 V (z. B. 5 368 709 120 mV) werden beim
Import immer verworfen, genau wie beim Live-Empfang.

Gefragt wird nach dem **Passwort der Kurs-Datenbank**. Das Tool erkennt Zeit-, Geräte-, Strom- und
Spannungsspalten und die Einheiten (V/mV, A/mA) selbst. Mehrfaches Ausführen ist unschädlich
(vorhandene Zeilen werden übersprungen). Klappt die Erkennung nicht, gibt es die Tabellenstruktur
aus – damit lässt sich die Zuordnung per `--table` bzw. `import_data sql --query` festlegen.

## 3. Ansehen

- Frontend: `http://212.227.31.76:20800`
- Läuft der Live-Empfang? `docker compose logs -f collector`
  - `subscription to 'traffic-nodes/+/measurements' confirmed` → verbunden, wartet auf Nachrichten
    (Node 101 sendet alle 15 Minuten)
  - `rejected message … voltage_mV = 5368709120 …` → Nachricht kam an, Werte unplausibel
    (Node misst gerade keinen Akku); das Gerät erscheint trotzdem im Frontend, mit Hinweis
  - `cannot reach MQTT broker` → Server/Port/TLS prüfen
  - `broker refused subscription` → Topic für unseren Benutzer nicht freigegeben

## Auf die Datenbank zugreifen (z. B. mit DBeaver/pgAdmin)

Standardmäßig ist unsere Datenbank nur auf dem Server selbst erreichbar. Vom eigenen Rechner aus
per SSH-Tunnel:

```bash
ssh -L 20832:127.0.0.1:20832 tinf25d-llv@212.227.31.76
```

Solange das Fenster offen ist: Host `localhost`, Port `20832`, Datenbank `batterywatch`,
Benutzer `batterywatch`, Passwort auf dem Server mit `grep POSTGRES_PASSWORD .env`.

Soll sie stattdessen direkt erreichbar sein: in `.env` `DB_BIND=0.0.0.0` setzen und
`docker compose up -d db` – dann ist sie unter `212.227.31.76:20832` offen im Internet,
nur durch das Passwort geschützt.

## Aktualisieren / Verwalten

```bash
systemctl --user start batterywatch-update.service   # sofort aktualisieren statt auf den Timer zu warten
# Zurück auf eine ältere Version: in .env  IMAGE_TAG=<Commit-Nummer>  setzen, dann: docker compose up -d
docker compose ps                      # Status
docker compose logs -f api             # Logs eines Dienstes
docker compose down                    # stoppen (Daten bleiben erhalten)
```

`docker compose down -v` löscht zusätzlich **alle Daten** unserer Datenbank.
