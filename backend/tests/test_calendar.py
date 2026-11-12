"""Calendar: expected failures (F12, issue #11) and private appointments (F13, issue #12).

Rules checked here:
  - every device in the list carries the prediction, so the calendar can show
    "wird kritisch" and "voraussichtlich leer" for all devices at once
  - technicians only see the prediction of their own devices (the list is filtered)
  - appointments are private: only the technician who made them sees them,
    management and admin get 403, other technicians 404
  - new appointments only for devices assigned to the technician
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from .conftest import user_id
from .test_auth import add_measurements

WHEN = "2026-11-17T08:30:00+01:00"


def ts(text: str) -> datetime:
    """Parse an API timestamp ("...Z" is only understood by Python >= 3.11 itself)."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def assign(db, device_id, username):
    db.execute("UPDATE devices SET technician_id = %s WHERE device_id = %s", (user_id(db, username), device_id))


# --- F12: prediction for all devices -------------------------------------------------------
def test_device_list_contains_prediction(make_client, db_url):
    chef = make_client("chef")
    add_measurements(db_url, "101", hours=72, volts_start=12.0, volts_end=11.7)  # -0.1 V/day
    add_measurements(db_url, "102", hours=72, volts_start=12.4, volts_end=12.4)  # flat: no estimate
    devices = {d["device_id"]: d for d in chef.get("/api/devices").json()}

    falling = devices["101"]
    assert falling["voltage_trend_v_per_day"] == pytest.approx(-0.1, abs=0.005)
    critical = ts(falling["estimated_critical_at"])
    empty = ts(falling["estimated_empty_at"])
    assert timedelta(days=7) < critical - datetime.now(timezone.utc) < timedelta(days=8.5)
    assert empty > critical

    flat = devices["102"]
    assert flat["estimated_critical_at"] is None and flat["estimated_empty_at"] is None

    # list and detail page give the same prediction
    detail = chef.get("/api/devices/101").json()
    assert detail["estimated_critical_at"] == falling["estimated_critical_at"]


def test_already_critical_device_is_due_now_even_without_trend(make_client, db_url):
    chef = make_client("chef")
    add_measurements(db_url, "101", hours=72, volts_start=10.8, volts_end=10.8)  # flat, ~14 %
    d = chef.get("/api/devices").json()[0]
    assert d["status"] == "krit"
    assert d["estimated_critical_at"] == d["last_seen"]  # due now
    assert d["estimated_empty_at"] is None  # not empty yet, voltage not falling


def test_technician_sees_prediction_only_for_own_devices(make_client, db, db_url):
    tech = make_client("techniker", "elif")
    add_measurements(db_url, "101", hours=24)
    add_measurements(db_url, "102", hours=24)
    assign(db, "101", "elif")
    assert [d["device_id"] for d in tech.get("/api/devices").json()] == ["101"]


# --- F13: private appointments --------------------------------------------------------------
def test_technician_creates_lists_changes_and_deletes_appointment(make_client, db, db_url):
    tech = make_client("techniker", "elif")
    add_measurements(db_url, "101", hours=3)
    assign(db, "101", "elif")

    r = tech.post("/api/appointments", json={"device_id": "101", "starts_at": WHEN, "note": "  Ersatzakku mitnehmen "})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["device_id"] == "101" and a["note"] == "Ersatzakku mitnehmen" and a["assigned"] is True
    assert ts(a["starts_at"]) == ts(WHEN)

    assert [x["id"] for x in tech.get("/api/appointments").json()] == [a["id"]]
    # time range filter (from inclusive, to exclusive)
    assert tech.get("/api/appointments", params={"from": "2026-11-18T00:00:00Z"}).json() == []
    assert len(tech.get("/api/appointments", params={"from": "2026-11-01T00:00:00Z",
                                                     "to": "2026-12-01T00:00:00Z"}).json()) == 1

    moved = tech.patch(f"/api/appointments/{a['id']}", json={"starts_at": "2026-11-18T13:30:00+01:00"}).json()
    assert moved["note"] == "Ersatzakku mitnehmen"  # unchanged
    assert ts(moved["starts_at"]) == ts("2026-11-18T13:30:00+01:00")
    cleared = tech.patch(f"/api/appointments/{a['id']}", json={"note": ""}).json()
    assert cleared["note"] is None
    assert tech.patch(f"/api/appointments/{a['id']}", json={"starts_at": None}).status_code == 400

    assert tech.delete(f"/api/appointments/{a['id']}").status_code == 204
    assert tech.get("/api/appointments").json() == []


def test_appointments_only_for_own_devices(make_client, db, db_url):
    tech = make_client("techniker", "elif")
    make_client("techniker", "jonas")
    add_measurements(db_url, "101", hours=3)
    add_measurements(db_url, "102", hours=3)
    assign(db, "101", "jonas")  # 102 stays unassigned
    for device in ("101", "102"):
        r = tech.post("/api/appointments", json={"device_id": device, "starts_at": WHEN})
        assert r.status_code == 403, device
    assert tech.post("/api/appointments", json={"device_id": "NOPE", "starts_at": WHEN}).status_code == 404
    assert tech.post("/api/appointments", json={"device_id": "101"}).status_code == 422  # no time


def test_appointments_are_private(make_client, db, db_url):
    elif_ = make_client("techniker", "elif")
    jonas = make_client("techniker", "jonas")
    add_measurements(db_url, "101", hours=3)
    assign(db, "101", "elif")
    a = elif_.post("/api/appointments", json={"device_id": "101", "starts_at": WHEN}).json()

    # another technician: doesn't see it, can't change or delete it (404, not even 403)
    assert jonas.get("/api/appointments").json() == []
    assert jonas.patch(f"/api/appointments/{a['id']}", json={"note": "x"}).status_code == 404
    assert jonas.delete(f"/api/appointments/{a['id']}").status_code == 404
    # Firmenchef, Mitarbeiter, Admin: no access to the private calendar at all
    for role in ("chef", "mitarbeiter", "admin"):
        client = make_client(role)
        assert client.get("/api/appointments").status_code == 403, role
        assert client.post("/api/appointments", json={"device_id": "101", "starts_at": WHEN}).status_code == 403
        assert client.delete(f"/api/appointments/{a['id']}").status_code == 403
    assert len(elif_.get("/api/appointments").json()) == 1  # still there


def test_reassigned_device_keeps_appointment_but_marks_it(make_client, db, db_url):
    tech = make_client("techniker", "elif")
    make_client("techniker", "jonas")
    add_measurements(db_url, "101", hours=3)
    assign(db, "101", "elif")
    tech.post("/api/appointments", json={"device_id": "101", "starts_at": WHEN})
    assign(db, "101", "jonas")
    [a] = tech.get("/api/appointments").json()
    assert a["assigned"] is False  # the page shows "nicht mehr zugeordnet"


def test_deleting_device_or_user_deletes_appointments(make_client, db, db_url):
    tech = make_client("techniker", "elif")
    chef = make_client("chef")
    add_measurements(db_url, "101", hours=3)
    assign(db, "101", "elif")
    tech.post("/api/appointments", json={"device_id": "101", "starts_at": WHEN})
    assert chef.delete("/api/devices/101").status_code == 204
    assert db.execute("SELECT count(*) FROM appointments").fetchone()[0] == 0
