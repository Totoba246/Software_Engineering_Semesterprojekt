"""Login, roles and user management (F06, F07, F09, ADR-09).

ADR-09 asks for targeted tests of: wrong password, other people's devices,
missing rights. Each test states the rule it checks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from batterywatch.contract import build_payload, build_topic, parse_message
from batterywatch.db import MeasurementStore
from batterywatch.tools import manage

from .conftest import TEST_PASSWORD, user_id


def add_measurements(db_url, device_id, hours=72, volts_start=12.0, volts_end=11.7):
    """Falling voltage every 3 min up to now (enough for trend + prediction)."""
    store = MeasurementStore(db_url)
    end = datetime.now(timezone.utc).replace(microsecond=0)
    steps = hours * 20
    for k in range(steps + 1):
        at = end - timedelta(minutes=3 * (steps - k))
        volts = volts_start + (volts_end - volts_start) * k / steps
        store.save(parse_message(build_topic(device_id), build_payload(600, volts * 1000, at)))
    store.close()


# --- login ---------------------------------------------------------------------------
def test_everything_needs_login_except_health(make_client):
    anon = make_client()
    assert anon.get("/api/health").status_code == 200
    for path in ("/api/devices", "/api/devices/101", "/api/status-rules", "/api/users", "/api/auth/me"):
        assert anon.get(path).status_code == 401, path


def test_login_wrong_password_and_unknown_user(make_client):
    make_client("chef")
    anon = make_client()
    assert anon.post("/api/auth/login", json={"username": "chef", "password": "falsch123"}).status_code == 401
    assert anon.post("/api/auth/login", json={"username": "gibtsnicht", "password": "x"}).status_code == 401


def test_login_cookie_me_and_logout(make_client):
    client = make_client("mitarbeiter", "Sarah.K")  # usernames are case-insensitive
    me = client.get("/api/auth/me").json()
    assert me["username"] == "sarah.k" and me["role"] == "mitarbeiter"
    cookie = client.cookies.get("bw_session")
    assert cookie and len(cookie) > 30
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_too_many_wrong_passwords_block_the_username(make_client):
    make_client("chef")
    anon = make_client()
    for _ in range(5):
        assert anon.post("/api/auth/login", json={"username": "chef", "password": "falsch"}).status_code == 401
    # even the right password is refused for a few minutes now
    r = anon.post("/api/auth/login", json={"username": "chef", "password": TEST_PASSWORD})
    assert r.status_code == 429 and "Fehlversuche" in r.json()["detail"]


def test_start_password_must_be_changed_first(make_client):
    client = make_client("techniker", "neu", must_change=True)
    assert client.get("/api/auth/me").json()["must_change_password"] is True
    assert client.get("/api/devices").status_code == 403  # blocked until changed
    bad = client.post("/api/auth/password", json={"current_password": "falsch", "new_password": "neuesPasswort1"})
    assert bad.status_code == 400
    short = client.post("/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "kurz"})
    assert short.status_code == 400
    ok = client.post("/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "neuesPasswort1"})
    assert ok.status_code == 204
    assert client.get("/api/devices").status_code == 200


# --- roles: who sees which devices -------------------------------------------------------
def test_admin_has_no_device_access_and_others_no_user_admin(make_client):
    admin, chef, tech = make_client("admin"), make_client("chef"), make_client("techniker")
    assert admin.get("/api/devices").status_code == 403
    assert chef.get("/api/users").status_code == 403
    assert tech.get("/api/users").status_code == 403
    assert tech.get("/api/technicians").status_code == 403


def test_technician_sees_only_assigned_devices(make_client, db_url, db):
    chef = make_client("chef")
    tech = make_client("techniker", "elif")
    elif_id = user_id(db, "elif")
    add_measurements(db_url, "101", hours=2)
    add_measurements(db_url, "102", hours=2)
    assert chef.patch("/api/devices/101", json={"technician_id": elif_id}).status_code == 200

    assert [d["device_id"] for d in tech.get("/api/devices").json()] == ["101"]
    assert tech.get("/api/devices/101").status_code == 200
    for path in ("/api/devices/102", "/api/devices/102/history", "/api/devices/102/messages"):
        assert tech.get(path).status_code == 403, path
    # technicians can't change anything
    assert tech.patch("/api/devices/101", json={"name": "x"}).status_code == 403
    assert tech.delete("/api/devices/101").status_code == 403
    # the assigned technician is only shown to Firmenchef/Mitarbeiter (README F11)
    assert chef.get("/api/devices/101").json()["technician"] == {"id": elif_id, "display_name": "Elif"}
    assert tech.get("/api/devices/101").json()["technician"] is None


# --- device master data (Firmenchef / Mitarbeiter) ----------------------------------------
def test_add_edit_and_delete_device(make_client, db_url, db):
    chef = make_client("chef")
    make_client("techniker", "jonas")
    jonas = user_id(db, "jonas")

    # add a node before it ever sent anything (e.g. node 101 without GPS -> manual position)
    r = chef.post("/api/devices", json={"device_id": "101", "name": "BA-01 Hauptstraße", "category": "Baustellenampel",
                                        "location": "Rottweil", "latitude": 48.168, "longitude": 8.628,
                                        "technician_id": jonas})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "unbekannt" and d["position"]["source"] == "manuell"
    assert d["technician"]["id"] == jonas
    assert chef.post("/api/devices", json={"device_id": "101"}).status_code == 409   # exists
    assert chef.post("/api/devices", json={"device_id": "1 01"}).status_code == 422  # not a valid topic id

    # the collector's first message is stored for the registered device
    add_measurements(db_url, "101", hours=1)
    d = chef.get("/api/devices/101").json()
    assert d["measurement_count"] > 0 and d["name"] == "BA-01 Hauptstraße"

    # partial update: only the fields sent change, null clears
    r = chef.patch("/api/devices/101", json={"location": "Rottweil, Marktplatz", "technician_id": None})
    assert r.json()["location"] == "Rottweil, Marktplatz" and r.json()["technician"] is None
    assert r.json()["category"] == "Baustellenampel"
    assert chef.patch("/api/devices/101", json={"latitude": 48.1}).status_code == 400  # longitude missing
    assert chef.patch("/api/devices/101", json={"technician_id": user_id(db, "chef")}).status_code == 400  # not a technician

    assert chef.delete("/api/devices/101").status_code == 204
    assert chef.get("/api/devices/101").status_code == 404
    assert db.execute("SELECT count(*) FROM measurements WHERE device_id = '101'").fetchone()[0] == 0


def test_prediction_for_falling_voltage(make_client, db_url):
    chef = make_client("chef")
    add_measurements(db_url, "101", hours=72, volts_start=12.0, volts_end=11.7)  # -0.1 V/day
    d = chef.get("/api/devices/101").json()
    assert d["voltage_trend_v_per_day"] == pytest.approx(-0.1, abs=0.005)
    critical = datetime.fromisoformat(d["estimated_critical_at"])
    empty = datetime.fromisoformat(d["estimated_empty_at"])
    # 11.7 V -> 10.94 V (20 %) at 0.1 V/day = about 7.6 days; empty (10.5 V) after 12 days
    assert timedelta(days=7) < critical - datetime.now(timezone.utc) < timedelta(days=8.5)
    assert empty > critical


# --- user management (admin) --------------------------------------------------------------
def test_admin_creates_user_with_start_password(make_client):
    admin = make_client("admin")
    r = admin.post("/api/users", json={"username": "Mueller", "display_name": "Max Müller", "role": "techniker"})
    assert r.status_code == 201, r.text
    start_password = r.json()["start_password"]
    assert r.json()["username"] == "mueller" and r.json()["must_change_password"] is True

    new = make_client()
    assert new.post("/api/auth/login", json={"username": "mueller", "password": start_password}).status_code == 200
    assert new.get("/api/devices").status_code == 403  # must change the start password first

    assert admin.post("/api/users", json={"username": "mueller", "display_name": "X", "role": "chef"}).status_code == 409
    assert admin.post("/api/users", json={"username": "a b", "display_name": "X", "role": "chef"}).status_code == 400
    assert admin.post("/api/users", json={"username": "kurz", "display_name": "X", "role": "chef",
                                          "password": "123"}).status_code == 400
    assert admin.post("/api/users", json={"username": "x1", "display_name": "X", "role": "kaiser"}).status_code == 422


def test_lock_and_reset_password_log_the_user_out(make_client, db):
    admin = make_client("admin")
    chef = make_client("chef")
    chef_id = user_id(db, "chef")

    assert admin.patch(f"/api/users/{chef_id}", json={"active": False}).status_code == 200
    assert chef.get("/api/devices").status_code == 401  # logged out immediately
    r = make_client().post("/api/auth/login", json={"username": "chef", "password": TEST_PASSWORD})
    assert r.status_code == 403 and "gesperrt" in r.json()["detail"]

    r = admin.patch(f"/api/users/{chef_id}", json={"active": True, "reset_password": True})
    new_password = r.json()["start_password"]
    assert new_password and r.json()["must_change_password"] is True
    assert make_client().post("/api/auth/login", json={"username": "chef", "password": TEST_PASSWORD}).status_code == 401
    assert make_client().post("/api/auth/login", json={"username": "chef", "password": new_password}).status_code == 200


def test_admin_cannot_lock_out_themselves_or_the_last_admin(make_client, db):
    admin = make_client("admin")
    me = user_id(db, "admin")
    assert admin.patch(f"/api/users/{me}", json={"active": False}).status_code == 400
    assert admin.patch(f"/api/users/{me}", json={"role": "chef"}).status_code == 400
    assert admin.delete(f"/api/users/{me}").status_code == 400
    assert admin.patch(f"/api/users/{me}", json={"display_name": "Chef-Admin"}).status_code == 200  # name is fine

    second = admin.post("/api/users", json={"username": "admin2", "display_name": "Zweiter", "role": "admin"}).json()
    assert admin.delete(f"/api/users/{second['id']}").status_code == 204  # another admin remains (me)


def test_removing_a_technician_unassigns_their_devices(make_client, db_url, db):
    admin, chef = make_client("admin"), make_client("chef")
    make_client("techniker", "elif")
    make_client("techniker", "jonas")
    add_measurements(db_url, "101", hours=1)
    add_measurements(db_url, "102", hours=1)
    chef.patch("/api/devices/101", json={"technician_id": user_id(db, "elif")})
    chef.patch("/api/devices/102", json={"technician_id": user_id(db, "jonas")})

    users = {u["username"]: u for u in admin.get("/api/users").json()}
    assert users["elif"]["device_count"] == 1

    admin.patch(f"/api/users/{user_id(db, 'elif')}", json={"role": "mitarbeiter"})  # no longer a technician
    admin.delete(f"/api/users/{user_id(db, 'jonas')}")
    assert [d["technician"] for d in chef.get("/api/devices").json()] == [None, None]


# --- command line tool ---------------------------------------------------------------------
def test_manage_cli_create_user_and_seed_demo(db_url, db, monkeypatch, capsys):
    monkeypatch.setenv("BW_PASSWORD", "adminpasswort")
    assert manage.main(["--database-url", db_url, "count-users"]) == 0
    assert capsys.readouterr().out.strip() == "0"
    manage.main(["--database-url", db_url, "create-user", "admin", "--role", "admin", "--name", "Administrator"])
    manage.main(["--database-url", db_url, "seed-demo"])
    roles = dict(db.execute("SELECT username, role FROM users").fetchall())
    assert roles == {"admin": "admin", "chef": "chef", "mitarbeiter": "mitarbeiter",
                     "techniker1": "techniker", "techniker2": "techniker"}
    assigned = db.execute("SELECT count(*) FROM devices WHERE device_id LIKE 'SIM-%' AND technician_id IS NOT NULL")
    assert assigned.fetchone()[0] == 7  # SIM-006 deliberately has no technician
    manage.main(["--database-url", db_url, "seed-demo"])  # running it again is harmless
    assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 5
