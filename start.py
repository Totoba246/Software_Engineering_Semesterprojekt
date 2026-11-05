#!/usr/bin/env python3
"""
BatteryWatch on YOUR OWN COMPUTER - one script for everything.

NEEDS
    - Docker Desktop, installed and RUNNING (whale icon in the taskbar)
      https://www.docker.com/products/docker-desktop/
    - Python 3 (you have it already)

USE (in a terminal, in the project folder, e.g. the VS Code terminal)
    python start.py                  start everything, open the web page
                                     (first time: asks a few questions)
    python start.py stop             stop everything (data is kept)
    python start.py status           what is running?
    python start.py logs             watch incoming messages (Ctrl+C to stop watching)
    python start.py mode real        receive the REAL node 101 (course broker, needs MQTT password)
    python start.py mode test        use 8 FAKE nodes instead (no internet/password needed)
    python start.py check-history    plausibility report of the course history database
    python start.py import-history   copy the course history into your local database
                                     (optional: --to 2026-03-29T00:16:57+00:00)
    python start.py reset            DELETE all local data and start fresh

WHAT RUNS WHERE (all on your computer, see docs/How-it-works.md)
    http://localhost:20800        the web page
    http://localhost:20801/docs   the API (clickable documentation)
    localhost:20832               the database (e.g. for DBeaver; password in .env)
    localhost:20883               the local test MQTT broker

This script only calls `docker compose ...` (see docker-compose.yml) and
writes the settings file .env. Only Python's standard library is used.
"""

from __future__ import annotations

import getpass
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # the project folder
ENV_FILE = ROOT / ".env"                        # our settings (with passwords, not in Git)
ENV_TEMPLATE = ROOT / ".env.example"            # the template it's made from

COURSE_BROKER = "mqtt.ti-labs.ai"               # where the real nodes publish
COURSE_SERVER = "212.227.31.76"                 # course server (only for the history database)
COURSE_USER = "tinf25d-llv"                     # our group's login (SSH, MQTT, history DB)
# local end of the SSH tunnel to the history DB (BW_TUNNEL_PORT only for testing)
TUNNEL_PORT = int(os.environ.get("BW_TUNNEL_PORT", "15432"))
BACKEND = ROOT / "backend"                      # our Python code


# --- small helpers -------------------------------------------------------------
def say(text: str) -> None:
    print(f"\n==> {text}", flush=True)


def fail(text: str) -> None:
    print(f"\nFEHLER: {text}", file=sys.stderr)
    sys.exit(1)


def ask(question: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    answer = input(f"{question}{hint}: ").strip()
    return answer or default


def yes(question: str, default: bool = True) -> bool:
    answer = ask(question + (" (J/n)" if default else " (j/N)")).lower()
    return default if not answer else answer.startswith(("j", "y"))


def compose(*args: str, check: bool = True, env: dict | None = None) -> int:
    """Run `docker compose <args>` in the project folder and show its output."""
    cmd = ["docker", "compose", *args]
    print("   $ " + " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=ROOT, env={**os.environ, **(env or {})})
    if check and result.returncode != 0:
        fail(f"'{' '.join(cmd)}' ist fehlgeschlagen (siehe Ausgabe oben).")
    return result.returncode


# --- the settings file .env ----------------------------------------------------
def read_env() -> dict[str, str]:
    values = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def set_env(**changes: str) -> None:
    """Change KEY=value lines in .env, keep everything else (comments too)."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in changes:
            lines[i] = f"{key}={changes[key]}"
            done.add(key)
    lines += [f"{k}={v}" for k, v in changes.items() if k not in done]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def is_real_mode(env: dict[str, str]) -> bool:
    return env.get("COLLECTOR_MQTT_HOST", "mqtt") != "mqtt"


def configure_mode(real: bool) -> None:
    """Point the collector at the course broker (real) or our test broker (test)."""
    if real:
        print("\nEcht-Modus: der Collector hört auf den Kurs-Broker und empfängt Node 101.")
        password = getpass.getpass(f"MQTT-Passwort für {COURSE_USER} (Eingabe bleibt unsichtbar): ")
        if not password:
            fail("Kein Passwort eingegeben.")
        set_env(COLLECTOR_MQTT_HOST=COURSE_BROKER, COLLECTOR_MQTT_PORT="8883", COLLECTOR_MQTT_TLS="true",
                COLLECTOR_MQTT_USERNAME=COURSE_USER, COLLECTOR_MQTT_PASSWORD=password)
    else:
        print("\nTest-Modus: 8 erfundene Nodes (SIM-001 ... SIM-008) senden an den lokalen Test-Broker.")
        set_env(COLLECTOR_MQTT_HOST="mqtt", COLLECTOR_MQTT_PORT="1883", COLLECTOR_MQTT_TLS="false",
                COLLECTOR_MQTT_USERNAME="", COLLECTOR_MQTT_PASSWORD="")


def first_time_setup() -> None:
    say("Erster Start: lege die Einstellungsdatei .env an")
    print("(.env enthält Passwörter und wird NICHT nach GitHub hochgeladen.)")
    shutil.copyfile(ENV_TEMPLATE, ENV_FILE)
    # a random password for the local database - nobody has to remember it
    set_env(POSTGRES_PASSWORD=secrets.token_hex(16))
    print("\nWelche Daten sollen ankommen?")
    print("  j = ECHTE Daten von Node 101 (Kurs-Broker, braucht das MQTT-Passwort)")
    print("  n = TEST-Daten von 8 erfundenen Nodes (geht immer, ohne Passwort)")
    configure_mode(yes("Echte Daten empfangen?", default=True))


# --- checks --------------------------------------------------------------------
def check_docker() -> None:
    if shutil.which("docker") is None:
        fail("Docker ist nicht installiert. Bitte Docker Desktop installieren: "
             "https://www.docker.com/products/docker-desktop/")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        fail("Docker läuft nicht. Bitte Docker Desktop starten (Wal-Symbol) und kurz warten.")


def wait_for_api(port: str, seconds: int = 120) -> bool:
    url = f"http://localhost:{port}/api/health"
    for _ in range(seconds):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(1)
    return False


# --- commands ------------------------------------------------------------------
def cmd_start() -> None:
    check_docker()
    if not ENV_FILE.exists():
        first_time_setup()
    env = read_env()
    real = is_real_mode(env)

    say("Baue und starte alle Teile (beim ersten Mal dauert das einige Minuten)")
    compose("up", "-d", "--build", "--remove-orphans")
    if not real:
        # fake nodes: 30 days of history once, then a message every 30 s
        compose("--profile", "test", "up", "-d", "--build", "publisher")
    else:
        compose("--profile", "test", "stop", "publisher", check=False)

    say("Warte, bis die API antwortet")
    api_port = env.get("API_PORT", "20801")
    if not wait_for_api(api_port):
        fail("Die API antwortet nicht. Details: docker compose logs api")

    web = f"http://localhost:{env.get('WEB_PORT', '20800')}"
    print(f"""
Fertig! BatteryWatch läuft auf deinem Computer.

  Webseite:     {web}
  API-Doku:     http://localhost:{api_port}/docs
  Modus:        {'ECHT - Node 101 vom Kurs-Broker (sendet alle 15 Min.)' if real else 'TEST - 8 erfundene Nodes'}

  Eingehende Nachrichten ansehen:   python start.py logs
  Stoppen:                          python start.py stop
""")
    webbrowser.open(web)


def cmd_stop() -> None:
    check_docker()
    say("Stoppe alles (die Daten bleiben erhalten)")
    compose("--profile", "test", "--profile", "tools", "down")


def cmd_status() -> None:
    check_docker()
    compose("--profile", "test", "ps")
    env = read_env()
    print(f"\nModus: {'ECHT (Kurs-Broker)' if is_real_mode(env) else 'TEST (erfundene Nodes)'}")


def cmd_logs() -> None:
    check_docker()
    print("Zeigt laufend, was der Collector empfängt. Beenden mit Strg+C.\n")
    try:
        compose("logs", "-f", "--tail", "30", "collector", check=False)
    except KeyboardInterrupt:
        pass


def cmd_mode(which: str) -> None:
    if which not in ("real", "test"):
        fail("Bitte 'python start.py mode real' oder 'python start.py mode test'.")
    if not ENV_FILE.exists():
        fail("Noch nicht eingerichtet - zuerst 'python start.py' ausführen.")
    configure_mode(which == "real")
    cmd_start()


def cmd_reset() -> None:
    check_docker()
    print("\nACHTUNG: löscht ALLE lokalen Daten (Datenbank, Test-Broker).")
    if not yes("Wirklich alles löschen?", default=False):
        print("Abgebrochen.")
        return
    compose("--profile", "test", "--profile", "tools", "down", "-v")
    print("Gelöscht. Neu starten mit: python start.py")


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def cmd_history(extra_args: list[str]) -> None:
    """Read the course history database through an SSH tunnel.

    The history database only listens on the course server itself (127.0.0.1:5432
    THERE). An SSH tunnel makes it appear on YOUR computer at localhost:15432:
        your computer :15432  ==(encrypted SSH connection)==>  server :5432
    The import tool then runs with YOUR Python if the libraries are installed
    (backend/requirements-dev.txt) - it reaches the tunnel directly at 127.0.0.1.
    Otherwise it runs in a Docker container, which reaches your computer's
    localhost under the special name "host.docker.internal".
    """
    check_docker()
    if not ENV_FILE.exists():
        fail("Noch nicht eingerichtet - zuerst 'python start.py' ausführen.")
    compose("up", "-d", "db")  # our local database must be running for the import

    tunnel = None
    if _port_open(TUNNEL_PORT):
        print(f"(Port {TUNNEL_PORT} ist schon offen - verwende den bestehenden Tunnel.)")
    else:
        if shutil.which("ssh") is None:
            fail("Das Programm 'ssh' fehlt (bei Windows 10/11 normalerweise eingebaut).")
        say(f"Öffne SSH-Tunnel zum Kursserver {COURSE_SERVER}")
        print(f"Gleich fragt ssh nach dem SSH-PASSWORT für {COURSE_USER} (Eingabe bleibt unsichtbar).")
        print("Bei der allerersten Verbindung evtl. vorher 'yes' eingeben.\n")
        tunnel = subprocess.Popen([
            "ssh", "-N",                                    # -N: only the tunnel, no remote shell
            "-L", f"{TUNNEL_PORT}:127.0.0.1:5432",          # local 15432 -> server's 127.0.0.1:5432
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ServerAliveInterval=30",
            f"{COURSE_USER}@{COURSE_SERVER}",
        ])
        for _ in range(120):                                # wait until the tunnel is up
            if tunnel.poll() is not None:
                fail("SSH-Verbindung fehlgeschlagen (Passwort falsch oder Server nicht erreichbar?).")
            if _port_open(TUNNEL_PORT):
                break
            time.sleep(1)
        else:
            tunnel.terminate()
            fail("Der Tunnel kam nicht zustande.")
        print("Tunnel steht.")

    try:
        password = ask_course_db_password()
        say("Lese die Kurs-Datenbank")
        run_import_tool(["history", *extra_args], password)
    finally:
        if tunnel is not None:
            tunnel.terminate()
            print("\nSSH-Tunnel geschlossen.")


def ask_course_db_password() -> str:
    """Ask for the course database password; if possible, check it right away
    (with the tunnel still open) and ask again if it's wrong - max. 3 tries."""
    for attempt in range(1, 4):
        password = getpass.getpass("\nPasswort der Kurs-DATENBANK (postgres, nicht SSH): ").strip()
        if not _native_python_ready():
            return password  # can't test it here; the Docker fallback will report errors
        probe = subprocess.run(
            [sys.executable, "-c",
             "import os, psycopg; psycopg.connect(os.environ['SOURCE_DSN'], connect_timeout=15).close()"],
            env={**os.environ, "SOURCE_DSN": f"host=127.0.0.1 port={TUNNEL_PORT} dbname=measurements "
                                             f"user={COURSE_USER} password={password}"},
            capture_output=True, text=True,
        )
        if probe.returncode == 0:
            print("Passwort ok.")
            return password
        if "password authentication failed" in probe.stderr:
            print(f"Falsches Passwort (Versuch {attempt}/3). Achtung: hier das POSTGRES-Passwort, "
                  "nicht das SSH-Passwort. Die Eingabe ist unsichtbar - einfach neu tippen oder einfügen.")
        else:
            fail("Verbindung zur Kurs-Datenbank fehlgeschlagen:\n" + probe.stderr.strip()[-600:])
    fail("Dreimal falsches Passwort - abgebrochen.")
    return ""


def _native_python_ready() -> bool:
    """Are our backend libraries installed in the Python running this script?"""
    probe = subprocess.run([sys.executable, "-c", "import psycopg, psycopg_pool, pydantic, paho.mqtt"],
                           cwd=BACKEND, capture_output=True)
    return probe.returncode == 0


def run_import_tool(args: list[str], source_password: str) -> int:
    """Run backend/batterywatch/tools/import_data.py with the given arguments.

    Passwords are handed over as environment variables (not as arguments),
    so they don't show up in process lists.
    """
    env = read_env()
    source = "dbname=measurements user={u} password={p} port={port} host=".format(
        u=COURSE_USER, p=source_password, port=TUNNEL_PORT)
    if _native_python_ready():
        # Your own Python: reaches the tunnel and our database directly on this computer.
        print("(mit deinem Python, ohne Docker-Container)")
        local_db = "postgresql://{u}:{p}@127.0.0.1:{port}/{db}".format(
            u=env.get("POSTGRES_USER", "batterywatch"), p=env.get("POSTGRES_PASSWORD", ""),
            port=env.get("DB_PORT", "20832"), db=env.get("POSTGRES_DB", "batterywatch"))
        return subprocess.run(
            [sys.executable, "-m", "batterywatch.tools.import_data", *args], cwd=BACKEND,
            env={**os.environ, "SOURCE_DSN": source + "127.0.0.1", "DATABASE_URL": local_db},
        ).returncode
    # Fallback: inside a container; Docker Desktop's name for "this computer".
    print("(im Docker-Container - schneller wäre: python -m pip install -r backend/requirements-dev.txt)")
    return compose("--profile", "tools", "run", "--rm", "-e", "SOURCE_DSN", "tools",
                   "python", "-m", "batterywatch.tools.import_data", *args,
                   env={"SOURCE_DSN": source + "host.docker.internal"}, check=False)


COMMANDS = {
    "start": lambda args: cmd_start(),
    "stop": lambda args: cmd_stop(),
    "status": lambda args: cmd_status(),
    "logs": lambda args: cmd_logs(),
    "mode": lambda args: cmd_mode(args[0] if args else ""),
    "reset": lambda args: cmd_reset(),
    "check-history": lambda args: cmd_history(["--check", *args]),
    "import-history": lambda args: cmd_history(args),
}


def main() -> None:
    os.chdir(ROOT)
    name, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("start", [])
    if name in ("-h", "--help", "help") or name not in COMMANDS:
        print(__doc__)
        sys.exit(0 if name in ("-h", "--help", "help") else 1)
    try:
        COMMANDS[name](args)
    except KeyboardInterrupt:
        print("\nAbgebrochen.")


if __name__ == "__main__":
    main()
