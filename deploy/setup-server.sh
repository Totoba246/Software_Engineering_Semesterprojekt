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
#  WHAT IT DOES (deployment as in the professor's sketch, see docs/Server.md)
#   1. checks that Docker is available on the server
#   2. FIRST RUN ONLY: creates the settings file .env from .env.example:
#        - asks for the MQTT password (course broker mqtt.ti-labs.ai)
#        - invents a random password for OUR database
#        - asks whether the database should be reachable from the internet
#      .env stays on the server and is never uploaded to GitHub.
#      It also contains COMPOSE_FILE=docker-compose.server.yml, so every
#      `docker compose` command here uses the server version.
#   3. downloads the finished images from ghcr.io (built by GitHub, see
#      .github/workflows/deploy.yml) - asks for a read-only token if needed
#   4. starts all containers
#   5. installs the systemd timer that checks for new images every 5 minutes
#      (deploy/batterywatch-update.service + .timer)
#   6. waits until the API answers and prints the addresses
#
#  Running it again is harmless: .env is kept, your data is kept.
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
# The server runs the finished images from ghcr.io (not docker-compose.yml, which builds).
grep -q '^COMPOSE_FILE=' .env || set_env COMPOSE_FILE docker-compose.server.yml

say "Lade die fertigen Images von ghcr.io (von GitHub gebaut)"
if ! docker compose pull 2>/tmp/batterywatch-pull.log; then
  cat /tmp/batterywatch-pull.log
  if grep -qiE "denied|unauthorized" /tmp/batterywatch-pull.log; then
    echo
    echo "ghcr.io sagt 'denied'. Zwei mögliche Gründe:"
    echo "  a) GitHub hat die Images noch nicht gebaut -> auf GitHub unter 'Actions' prüfen,"
    echo "     ob der Workflow 'Deploy' grün durchgelaufen ist (läuft nach jedem Push auf main)."
    echo "     Dann hier Strg+C und das Skript später erneut starten."
    echo "  b) Die Images sind privat. Dafür braucht es einen"
    echo "NUR-LESE-Token (\"deploy-token [RO]\" in der Skizze):"
    echo "  GitHub -> Settings -> Developer settings -> Personal access tokens (classic)"
    echo "  -> Generate new token -> nur das Häkchen 'read:packages' setzen"
    echo "(Alternative ohne Token: GitHub -> Packages -> batterywatch-backend/-frontend"
    echo " -> Package settings -> Change visibility -> Public)"
    read -rp "GitHub-Benutzername: " gh_user
    read -rsp "Token (unsichtbar): " gh_token; echo
    printf '%s' "$gh_token" | docker login ghcr.io -u "$gh_user" --password-stdin || die "Anmeldung bei ghcr.io fehlgeschlagen."
    docker compose pull || die "Images konnten nicht geladen werden."
  else
    die "Images konnten nicht geladen werden. Läuft der Deploy-Workflow auf GitHub (Actions -> Deploy)?"
  fi
fi

say "Starte die Container"
docker compose up -d --remove-orphans

say "Richte das automatische Update ein (systemd-Timer, alle 5 Minuten)"
unit_dir="$HOME/.config/systemd/user"
mkdir -p "$unit_dir"
# the service file assumes ~/batterywatch; use the real folder instead
sed "s#%h/batterywatch#$PWD#" deploy/batterywatch-update.service > "$unit_dir/batterywatch-update.service"
cp deploy/batterywatch-update.timer "$unit_dir/"
if systemctl --user daemon-reload && systemctl --user enable --now batterywatch-update.timer; then
  # keep the timer running when nobody is logged in (may need admin rights)
  loginctl enable-linger "$USER" 2>/dev/null \
    || echo "Hinweis: 'loginctl enable-linger $USER' ging nicht - der Timer läuft dann nur, solange jemand eingeloggt ist. Ggf. Admin fragen."
  systemctl --user list-timers batterywatch-update.timer --no-pager || true
else
  echo "Hinweis: systemd-Benutzerdienste sind hier nicht verfügbar. Updates dann von Hand:"
  echo "  cd $PWD && git pull && docker compose pull && docker compose up -d"
fi

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
  Updates:    automatisch alle 5 Min. (push auf main -> GitHub baut -> Server holt es)
              Protokoll: journalctl --user -u batterywatch-update.service

Historische Daten aus der Kurs-Datenbank übernehmen:
  ./deploy/import-history.sh
EOF
