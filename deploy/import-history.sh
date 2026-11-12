#!/usr/bin/env bash
# =============================================================================
#  Copies the OLD measurements from the course database into OUR database.
# =============================================================================
#  Run it ON THE SERVER, in the batterywatch folder, after setup-server.sh.
#
#  The two databases:
#    course database  = 127.0.0.1:5432 on the server, database "measurements"
#                       (belongs to the course, we only READ from it)
#    our database     = 127.0.0.1:20832 on the server (our "db" container)
#  Both are only reachable from the server itself - that's why this must run there.
#
#  It asks for the course database password, then starts a short-lived
#  container with our import tool (backend/batterywatch/tools/import_data.py).
# =============================================================================
#
# Copies the historical measurements from the course's history database
# (PostgreSQL on the server, 127.0.0.1:5432) into our own BatteryWatch database.
#
#   ./deploy/import-history.sh                  # detect table/columns automatically and import
#   ./deploy/import-history.sh --inspect        # only show which tables/columns exist
#   ./deploy/import-history.sh --check          # plausibility report: from when on is the data garbage?
#   ./deploy/import-history.sh --to <time>      # import only up to that time (see --check)
#   ./deploy/import-history.sh --table <name>   # pick the table explicitly
#   ./deploy/import-history.sh --shift-to-now   # move the data so it ends today (demo)
#
# Safe to run repeatedly: rows that already exist are skipped.
set -euo pipefail
cd "$(dirname "$0")/.."

die() { printf '\n\033[31mFEHLER: %s\033[0m\n' "$*" >&2; exit 1; }

[ -f .env ] || die ".env fehlt – zuerst ./deploy/setup-server.sh ausführen."
set -a; . ./.env; set +a

api_container=$(docker compose ps -q api)
[ -n "$api_container" ] || die "Der Stack läuft nicht – zuerst ./deploy/setup-server.sh ausführen."
image=$(docker inspect --format '{{.Image}}' "$api_container")

read -rp "Host der Kurs-Datenbank [127.0.0.1]: " src_host
read -rp "Port [5432]: " src_port
read -rp "Datenbank [measurements]: " src_db
read -rp "Benutzer [tinf25d-llv]: " src_user
read -rsp "Passwort der Kurs-Datenbank: " src_password; echo

# Passed to the container as environment variables (not as arguments),
# so the passwords don't show up in the process list of the shared server.
export SOURCE_DSN="host=${src_host:-127.0.0.1} port=${src_port:-5432} dbname=${src_db:-measurements} user=${src_user:-tinf25d-llv} password=${src_password}"
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${DB_PORT:-20832}/${POSTGRES_DB}"

# --network host: inside the container 127.0.0.1 is the server itself,
# so both databases are reachable without opening any port.
docker run --rm --network host -e SOURCE_DSN -e DATABASE_URL "$image" \
  python -m batterywatch.tools.import_data history "$@"
