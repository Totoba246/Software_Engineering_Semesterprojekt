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

## 1. Einrichten (einmalig)

```bash
ssh tinf25d-llv@212.227.31.76
git clone -b claude/sleepy-brown-bvz71m https://github.com/Totoba246/Software_Engineering_Semesterprojekt.git batterywatch
cd batterywatch
./deploy/setup-server.sh
```

Das Skript fragt nach dem **MQTT-Passwort** (Enter übernimmt die Vorgaben in `[...]`), erzeugt ein
eigenes Passwort für unsere Datenbank, schreibt alles in `.env` und startet die Container.

## 2. Historische Daten übernehmen

```bash
./deploy/import-history.sh --inspect   # zeigt nur, welche Tabellen/Spalten es gibt
./deploy/import-history.sh             # übernimmt die Daten
```

Gefragt wird nach dem **Passwort der Kurs-Datenbank**. Das Tool erkennt Zeit-, Geräte-, Strom- und
Spannungsspalten und die Einheiten (V/mV, A/mA) selbst. Mehrfaches Ausführen ist unschädlich
(vorhandene Zeilen werden übersprungen). Klappt die Erkennung nicht, gibt es die Tabellenstruktur
aus – damit lässt sich die Zuordnung per `--table` bzw. `import_data sql --query` festlegen.

## 3. Ansehen

- Frontend: `http://212.227.31.76:20800`
- Läuft der Live-Empfang? `docker compose logs -f collector`
  - `subscription confirmed` → verbunden, wartet auf Nachrichten
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
git pull && ./deploy/setup-server.sh   # neue Version bauen und starten (.env bleibt)
docker compose ps                      # Status
docker compose logs -f api             # Logs eines Dienstes
docker compose down                    # stoppen (Daten bleiben erhalten)
```

`docker compose down -v` löscht zusätzlich **alle Daten** unserer Datenbank.
