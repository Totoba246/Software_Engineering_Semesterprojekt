# Entwicklung & Betrieb

```
TrafficNode / Testpublisher ──MQTT──▶ Mosquitto ──▶ Collector ──▶ PostgreSQL ◀── API (FastAPI) ◀── Frontend (React)
```

| Ordner | Inhalt |
|---|---|
| `backend/batterywatch/collector/` | Collection-Service: MQTT → Validierung → DB (ADR-10) |
| `backend/batterywatch/api/` | REST-API für das Frontend (ADR-06) |
| `backend/batterywatch/contract.py` | MQTT-Vertrag ([Doku](MQTT-Vertrag.md)) |
| `backend/batterywatch/battery.py` | U_bat-Formel, Ladezustand, Status ([Doku](Statusregeln.md)) |
| `backend/batterywatch/schema.sql` | Datenbankschema (wird beim Start automatisch angelegt) |
| `backend/batterywatch/tools/` | Testpublisher und Import-Tool |
| `frontend/` | React-App (Vite) |
| `docker-compose.yml` | gesamter Stack |

## Schnellstart mit Docker

```bash
cp .env.example .env          # Passwort setzen!
docker compose up -d --build
docker compose --profile test up -d publisher
```

- Frontend: http://localhost:20800
- API + interaktive Doku: http://localhost:20801/docs
- PostgreSQL: `localhost:20832`, MQTT: `localhost:20883` (beide nur lokal gebunden)

Die Ports liegen im Bereich der Gruppe **LLV (20800–20899)** auf dem Kursserver.

Der Testpublisher schreibt 30 Tage simulierte Historie für 8 Geräte direkt in die DB und
schickt danach alle 30 s echte MQTT-Nachrichten – damit ist der komplette Weg
Publisher → Broker → Collector → DB → API → Frontend getestet.

## Testdaten

Die echten Nodes senden gerade nicht. Es gibt drei Wege, an Daten zu kommen:

### a) Simulierte Nodes (Testpublisher, über MQTT)

```bash
cd backend
python -m batterywatch.tools.test_publisher simulate --devices 8 --backfill-hours 72 --interval 10
python -m batterywatch.tools.test_publisher simulate --once                  # Smoke-Test
python -m batterywatch.tools.test_publisher --invalid-every 20 simulate      # jede 20. Nachricht kaputt
python -m batterywatch.tools.test_publisher --dry-run simulate --once        # nur anzeigen
```

Das Batteriemodell ist an die echten TSN-002-Daten angelehnt: Tagstrom ≈ 0,63 A, nachts
gedimmt ≈ 0,52 A, Spannungsabfall ≈ 0,1 V/Tag, Batteriewechsel bei leerem Akku.
`--rate` (Standard 300 Nachrichten/s) bremst große Sendungen – Mosquitto verwirft sonst
QoS-1-Nachrichten, wenn die Warteschlange eines Abonnenten überläuft. Für lange Historie
`--backfill-direct` verwenden (schreibt direkt in `$DATABASE_URL`).

### b) Aufgezeichnete Beispieldaten (`docs/samples/traffic_devices_signals.csv`)

2 229 echte Messungen von TSN-002 (19.–24.03.2026, alle 3 Minuten).

```bash
# direkt in die DB importieren (--shift-to-now: Daten enden heute, Uhrzeiten bleiben erhalten)
python -m batterywatch.tools.import_data csv ../docs/samples/traffic_devices_signals.csv --shift-to-now

# oder über MQTT abspielen (testet den Collector), 600-fache Geschwindigkeit
python -m batterywatch.tools.test_publisher replay ../docs/samples/traffic_devices_signals.csv --shift-to-now --speed 600
```

Im Docker-Stack (Beispieldaten sind dort unter `/samples` eingebunden):

```bash
docker compose --profile test run --rm publisher python -m batterywatch.tools.import_data csv /samples/traffic_devices_signals.csv --shift-to-now
```

Ein erneuter Import erzeugt keine Duplikate (eindeutig je Gerät + Zeitstempel).

### c) Historien-Datenbank des Kurses

Die gemeinsame Historien-PostgreSQL (Port 5432, nur per SSH-Tunnel) lässt sich mit einer
SQL-Abfrage übernehmen. Die Abfrage muss die Spalten `device_id, measured_at, current_ma,
voltage_mv` liefern (optional `tenant, device_type, latitude, longitude, altitude_m, satellites`) –
Spaltennamen der Quelle per `AS` umbenennen:

```bash
ssh -L 15432:localhost:5432 <user>@<kursserver>

python -m batterywatch.tools.import_data sql \
  --source-dsn postgresql://<user>:<passwort>@localhost:15432/<db> \
  --query "SELECT device_id, time AS measured_at, current_a*1000 AS current_ma, voltage_v*1000 AS voltage_mv, latitude, longitude FROM <tabelle>"
```

(Tabellen-/Spaltennamen der Historien-DB sind noch zu prüfen, z. B. mit `\d` in `psql`.)

## Live-Broker des Kurses

Der Collector kann statt des lokalen Brokers den gemeinsamen Live-Broker (MQTT mit TLS,
Port 8883) abonnieren. In `.env` (Zugangsdaten aus `tinf25d-llv.yaml`, **nicht committen**):

```
COLLECTOR_MQTT_HOST=<host>
COLLECTOR_MQTT_PORT=8883
COLLECTOR_MQTT_TLS=true
COLLECTOR_MQTT_USERNAME=tinf25d-llv
COLLECTOR_MQTT_PASSWORD=...
```

Danach `docker compose up -d collector`. Den Testpublisher nicht gegen den gemeinsamen Broker laufen lassen.

## Lokale Entwicklung ohne Docker

Voraussetzungen: Python ≥ 3.11, Node ≥ 20, PostgreSQL und Mosquitto (oder nur `db` und `mqtt` aus Docker:
`docker compose up -d db mqtt`, dann `DATABASE_URL=postgresql://batterywatch:<pw>@localhost:20832/batterywatch`
und `MQTT_PORT=20883` verwenden).

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql://batterywatch:batterywatch@localhost:5432/batterywatch

python -m batterywatch.collector                           # Terminal 1
uvicorn batterywatch.api.main:app --reload --port 8000     # Terminal 2
python -m batterywatch.tools.test_publisher simulate --backfill-hours 72 --interval 10   # Terminal 3

cd ../frontend && npm install && npm run dev               # Terminal 4 → http://localhost:5173
```

## Tests

```bash
cd backend
pytest                                    # Unit-Tests (ohne Datenbank)

# + Integrationstests (DB wird geleert! eigene Test-DB verwenden)
TEST_DATABASE_URL=postgresql://batterywatch:batterywatch@localhost:5432/batterywatch_test pytest

# + Ende-zu-Ende über einen echten MQTT-Broker
TEST_DATABASE_URL=... TEST_MQTT_HOST=localhost pytest
```

Die GitHub-Action `.github/workflows/ci.yml` führt alle Tests (inkl. MQTT) und den Frontend-Build aus.

## REST-API

| Endpunkt | Inhalt |
|---|---|
| `GET /api/health` | Lebenszeichen inkl. DB |
| `GET /api/devices` | alle Geräte mit aktuellem Zustand (geglättete Spannung, SoC, Status, Position, letzte Meldung) |
| `GET /api/devices/{id}` | wie oben + Anzahl Messwerte, Ø-Strom 24 h, Spannungstrend V/Tag |
| `GET /api/devices/{id}/history?hours=168` | Verlauf, zu Zeitintervallen zusammengefasst (Mittel/Min/Max); Zeitraum endet bei der letzten Meldung |
| `GET /api/status-rules` | aktuell gültige Schwellwerte und Kennlinie |

Das Frontend fragt die Daten alle 5 Minuten neu ab (ADR-06).

## Datenbank

| Tabelle | Inhalt |
|---|---|
| `devices` | ein Eintrag je Gerät (wird beim ersten Messwert angelegt); `name`, `category`, `location` für Stammdaten (F07) |
| `measurements` | ein Eintrag je Nachricht: Rohwerte `current_ma`, `voltage_mv`, berechnet `battery_voltage_mv`, GPS, `source` (`mqtt`/`import`) |

Eindeutig je `(device_id, measured_at)`; der zugehörige Index trägt alle Abfragen „letzte Werte / Verlauf eines Geräts“.
