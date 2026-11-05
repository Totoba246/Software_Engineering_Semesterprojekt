#!/usr/bin/env bash
# =============================================================================
#  Sets up and starts BatteryWatch on the course server (or any Docker host).
# =============================================================================
#  HOW TO USE (type these on your laptop, one after another):
#    ssh tinf25d-llv@212.227.31.76        # log into the server (asks for the SSH password)
#    git clone -b claude/sleepy-brown-bvz71m https://github.com/Totoba246/Software_Engineering_Semesterprojekt.git batterywatch
#                                         # download our code into the folder "batterywatch"
#    cd batterywatch                      # go into that folder
#    ./deploy/setup-server.sh             # run this script
#
#  WHAT IT DOES
#   1. checks that Docker is available on the server
#   2. FIRST RUN ONLY: creates the settings file .env from .env.example:
#        - asks for the MQTT password (course broker mqtt.ti-labs.ai)
#        - invents a random password for OUR database
#        - asks whether the database should be reachable from the internet
#      .env stays on the server and is never uploaded to GitHub.
#   3. builds and starts all containers (docker compose up -d --build)
#   4. waits until the API answers and prints the addresses
#
#  Later runs (e.g. after `git pull` for a new version) keep .env and just
#  rebuild + restart. Your data in the database is kept.
# =============================================================================
set -euo pipefail          # stop at the first error instead of carrying on
cd "$(dirname "$0")/.."    # go to the project folder (one level above deploy/)

# say = print a bold heading, die = print a red error and stop
say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFEHLER: %s\033[0m\n' "$*" >&2; exit 1; }

# set KEY=VALUE in .env (replaces the line, keeps everything else)
set_env() {
  local key=$1 value=$2 tmp
  tmp=$(mktemp)
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ $line == "$key="* ]]; then printf '%s=%s\n' "$key" "$value"; else printf '%s\n' "$line"; fi
  done < .env > "$tmp"
  grep -q "^$key=" "$tmp" || printf '%s=%s\n' "$key" "$value" >> "$tmp"
  cat "$tmp" > .env && rm -f "$tmp"
}

say "Prüfe Docker"
command -v docker >/dev/null || die "Docker ist auf diesem Server nicht installiert."
docker info >/dev/null 2>&1 || die "Kein Zugriff auf Docker (läuft der Dienst? ist '$USER' in der Gruppe 'docker'?)."
docker compose version >/dev/null 2>&1 || die "'docker compose' (Compose v2) fehlt."

if [ ! -f .env ]; then
  say "Erstelle .env (Konfiguration mit Passwörtern, wird NICHT nach Git hochgeladen)"
  cp .env.example .env
  chmod 600 .env

  db_password=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
  set_env POSTGRES_PASSWORD "$db_password"

  read -rp "MQTT-Server [mqtt.ti-labs.ai]: " mqtt_host
  read -rp "MQTT-Port [8883]: " mqtt_port
  read -rp "MQTT-Benutzer [tinf25d-llv]: " mqtt_user
  read -rsp "MQTT-Passwort: " mqtt_password; echo
  [ -n "$mqtt_password" ] || die "Kein MQTT-Passwort eingegeben."
  set_env COLLECTOR_MQTT_HOST "${mqtt_host:-mqtt.ti-labs.ai}"
  set_env COLLECTOR_MQTT_PORT "${mqtt_port:-8883}"
  set_env COLLECTOR_MQTT_TLS true
  set_env COLLECTOR_MQTT_USERNAME "${mqtt_user:-tinf25d-llv}"
  set_env COLLECTOR_MQTT_PASSWORD "$mqtt_password"

  echo
  echo "Soll die Datenbank direkt aus dem Internet erreichbar sein (Port 20832)?"
  echo "  n = nur über SSH-Tunnel (empfohlen, so ist auch die Kurs-Datenbank eingerichtet)"
  echo "  j = öffentlich, nur durch das Passwort geschützt"
  read -rp "Öffentlich erreichbar? [n]: " public_db
  if [[ ${public_db:-n} =~ ^[jJyY] ]]; then set_env DB_BIND 0.0.0.0; fi
else
  say ".env existiert bereits – Einstellungen werden beibehalten"
  # upgrade settings from earlier versions of this script
  if grep -qx 'COLLECTOR_MQTT_TOPIC=traffic-device/+/+/+/status' .env; then
    set_env COLLECTOR_MQTT_TOPIC "traffic-nodes/+/measurements,traffic-device/+/+/+/status"
    echo "MQTT-Topic auf traffic-nodes/+/measurements umgestellt"
  fi
  if grep -qx 'STALE_AFTER_MINUTES=30' .env; then set_env STALE_AFTER_MINUTES 45; fi
fi

say "Baue und starte die Container (beim ersten Mal einige Minuten)"
docker compose up -d --build

say "Warte auf die API"
set -a; . ./.env; set +a
for _ in $(seq 1 60); do
  if curl -fs "http://127.0.0.1:${API_PORT:-20801}/api/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fs "http://127.0.0.1:${API_PORT:-20801}/api/health" >/dev/null || die "API antwortet nicht: docker compose logs api"

docker compose ps
host_ip=$(hostname -I 2>/dev/null | awk '{print $1}')
cat <<EOF

Fertig.
  Frontend:   http://${host_ip:-<server>}:${WEB_PORT:-20800}
  Datenbank:  ${DB_BIND:-127.0.0.1}:${DB_PORT:-20832}  Datenbank '${POSTGRES_DB}', Benutzer '${POSTGRES_USER}'
              Passwort steht in .env (POSTGRES_PASSWORD)
  Collector:  docker compose logs -f collector   (zeigt, ob der Live-Broker Nachrichten liefert)

Historische Daten aus der Kurs-Datenbank übernehmen:
  ./deploy/import-history.sh
EOF
