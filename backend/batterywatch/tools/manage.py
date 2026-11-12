"""Account management from the command line (for things the website can't do yet).

Normally you don't call this yourself:
  - `python start.py` creates the first admin on the very first start,
  - in test mode it offers demo accounts (seed-demo).
Everything else (new users, roles, locking, devices) is done on the website.

Examples (in Docker: docker compose exec api python -m batterywatch.tools.manage ...):
    python -m batterywatch.tools.manage count-users
    python -m batterywatch.tools.manage create-user admin --role admin --name Administrator
    python -m batterywatch.tools.manage reset-password mueller
    python -m batterywatch.tools.manage list-users
    python -m batterywatch.tools.manage seed-demo

Passwords are asked for invisibly, or read from the environment variable
BW_PASSWORD (so start.py can pass them without showing them in process lists).
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

import psycopg
from psycopg.rows import dict_row

from .. import security
from ..config import get_settings
from ..db import ensure_schema

DEMO_PASSWORD = "demo1234"
DEMO_USERS = [  # username, display name, role
    ("chef", "Thomas Weber", "chef"),
    ("mitarbeiter", "Sarah Klein", "mitarbeiter"),
    ("techniker1", "Elif Aydin", "techniker"),
    ("techniker2", "Jonas Brandt", "techniker"),
]
# Master data for the fake nodes SIM-001 ... SIM-008 of the test publisher
# (same order as its SITES list: the places match the simulated GPS positions).
DEMO_DEVICES = [  # name, category, location, technician username
    ("BA-01 Hauptstraße", "Baustellenampel", "Rottweil", "techniker1"),
    ("GA-02 Bickeberg", "Geschwindigkeitsanzeige", "Villingen-Schwenningen", "techniker2"),
    ("BA-03 Möhringer Straße", "Baustellenampel", "Tuttlingen", "techniker2"),
    ("VZ-04 B14 Nord", "Verkehrszählgerät", "Oberndorf am Neckar", "techniker1"),
    ("WL-05 Hauptstraße", "Warnleitanhänger", "Spaichingen", "techniker2"),
    ("BA-06 Lauterbacher Straße", "Baustellenampel", "Schramberg", None),
    ("GA-07 Wilhelmstraße", "Geschwindigkeitsanzeige", "Balingen", "techniker1"),
    ("BA-08 Neckarbrücke", "Baustellenampel", "Sulz am Neckar", "techniker1"),
]


def _connect(url: str | None) -> psycopg.Connection:
    conn = psycopg.connect(url or get_settings().database_url, row_factory=dict_row, autocommit=True)
    ensure_schema(conn)
    return conn


def _ask_password(confirm: bool = True) -> str:
    password = os.environ.get("BW_PASSWORD")
    if password is None:
        password = getpass.getpass("Passwort (unsichtbar): ")
        if confirm and getpass.getpass("Passwort wiederholen: ") != password:
            sys.exit("Die Passwörter stimmen nicht überein.")
    problem = security.check_password(password)
    if problem:
        sys.exit(problem)
    return password


def create_user(conn, username: str, display_name: str, role: str, password: str,
                email: str | None = None, must_change: bool = False) -> None:
    username = security.normalize_username(username)
    problem = security.check_username(username)
    if problem:
        sys.exit(problem)
    if role not in security.ROLES:
        sys.exit(f"Unbekannte Rolle {role!r}. Möglich: {', '.join(security.ROLES)}")
    conn.execute(
        "INSERT INTO users (username, display_name, email, role, password_hash, must_change_password) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (username, display_name, email, role, security.hash_password(password), must_change))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", help="default: $DATABASE_URL")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("count-users", help="print the number of accounts")
    sub.add_parser("list-users", help="show all accounts")
    p = sub.add_parser("create-user", help="create an account (password asked or from $BW_PASSWORD)")
    p.add_argument("username")
    p.add_argument("--role", required=True, choices=list(security.ROLES))
    p.add_argument("--name", help="display name (default: the username)")
    p.add_argument("--email")
    p.add_argument("--must-change", action="store_true", help="user must change the password at first login")
    p = sub.add_parser("reset-password", help="set a new password (asked or from $BW_PASSWORD), unlock the account")
    p.add_argument("username")
    sub.add_parser("seed-demo", help=f"demo accounts (password {DEMO_PASSWORD}) + master data for SIM-001...SIM-008")
    args = parser.parse_args(argv)

    with _connect(args.database_url) as conn:
        if args.cmd == "count-users":
            print(conn.execute("SELECT count(*) AS n FROM users").fetchone()["n"])

        elif args.cmd == "list-users":
            for u in conn.execute("SELECT username, display_name, role, active FROM users ORDER BY role, username"):
                state = "" if u["active"] else "  (gesperrt)"
                print(f"{u['username']:20} {security.ROLES[u['role']]:17} {u['display_name']}{state}")

        elif args.cmd == "create-user":
            exists = conn.execute("SELECT 1 FROM users WHERE username = %s",
                                  (security.normalize_username(args.username),)).fetchone()
            if exists:
                sys.exit(f"Den Benutzernamen {args.username} gibt es schon.")
            create_user(conn, args.username, args.name or args.username, args.role, _ask_password(),
                        args.email, args.must_change)
            print(f"Konto {args.username} ({security.ROLES[args.role]}) angelegt.")

        elif args.cmd == "reset-password":
            username = security.normalize_username(args.username)
            if not conn.execute("SELECT 1 FROM users WHERE username = %s", (username,)).fetchone():
                sys.exit(f"Den Benutzernamen {username} gibt es nicht.")
            conn.execute("UPDATE users SET password_hash = %s, active = true, must_change_password = false "
                         "WHERE username = %s", (security.hash_password(_ask_password()), username))
            conn.execute("DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE username = %s)", (username,))
            print(f"Neues Passwort für {username} gesetzt (Konto ist entsperrt).")

        elif args.cmd == "seed-demo":
            seed_demo(conn)
    return 0


def seed_demo(conn) -> None:
    """Demo accounts and master data for the fake nodes. ONLY for test mode:
    the demo password is public (it's in this file)."""
    ids = {}
    for username, name, role in DEMO_USERS:
        row = conn.execute("SELECT id FROM users WHERE username = %s", (username,)).fetchone()
        if row is None:
            create_user(conn, username, name, role, DEMO_PASSWORD)
            row = conn.execute("SELECT id FROM users WHERE username = %s", (username,)).fetchone()
        ids[username] = row["id"]
    for i, (name, category, location, tech) in enumerate(DEMO_DEVICES, start=1):
        conn.execute(
            "INSERT INTO devices (device_id, device_type, name, category, location, technician_id) "
            "VALUES (%s, 'trafficnode', %s, %s, %s, %s) ON CONFLICT (device_id) DO UPDATE SET "
            "name = EXCLUDED.name, category = EXCLUDED.category, location = EXCLUDED.location, "
            "technician_id = EXCLUDED.technician_id",
            (f"SIM-{i:03d}", name, category, location, ids.get(tech)))
    print("Demo-Konten (Passwort: " + DEMO_PASSWORD + "): " + ", ".join(u for u, _, _ in DEMO_USERS))
    print("Stammdaten für SIM-001 ... SIM-008 gesetzt und Servicetechnikern zugeordnet.")


if __name__ == "__main__":
    sys.exit(main())
