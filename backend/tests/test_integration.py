"""Integration tests against a real PostgreSQL (and optionally a real MQTT broker)."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from batterywatch.api.main import create_app
from batterywatch.collector.main import Collector, build_client
from batterywatch.config import Settings
from batterywatch.contract import build_payload, build_topic, parse_message
from batterywatch.db import MeasurementStore
from batterywatch.tools import import_data, test_publisher

from .conftest import SAMPLE_CSV

TOPIC = build_topic("demo", "trafficnode", "SIM-001")


def msg(at: datetime, current_ma=600.0, voltage_mv=11600.0, lat=48.2, lon=8.6) -> bytes:
    return build_payload(current_ma, voltage_mv, at, lat, lon, 600.0, 8).encode()


def make_settings(db_url: str, **kw) -> Settings:
    return Settings(database_url=db_url, **kw)


# --- Storage / collector ---------------------------------------------------
def test_store_computes_battery_voltage_and_ignores_duplicates(db_url, db):
    store = MeasurementStore(db_url)
    m = parse_message(TOPIC, msg(datetime(2026, 3, 19, 8, 0, tzinfo=timezone.utc), 551.0, 11276.0))
    assert store.save(m) is True
    assert store.save(m) is False  # same device + timestamp
    row = db.execute("SELECT voltage_mv, current_ma, battery_voltage_mv, source FROM measurements").fetchall()
    assert row == [(11276.0, 551.0, pytest.approx(11277.102), "mqtt")]
    assert db.execute("SELECT device_id, tenant, device_type FROM devices").fetchall() == [
        ("SIM-001", "demo", "trafficnode")
    ]


def test_collector_stores_valid_and_rejects_invalid(db_url, db):
    collector = Collector(make_settings(db_url), MeasurementStore(db_url))
    at = datetime(2026, 3, 19, 8, 0, tzinfo=timezone.utc)
    assert collector.handle_message(TOPIC, msg(at)) == "stored"
    assert collector.handle_message(TOPIC, msg(at)) == "duplicate"
    assert collector.handle_message(TOPIC, b'{"current_mA": 1}') == "rejected"
    assert collector.handle_message("wrong/topic", msg(at)) == "rejected"
    assert db.execute("SELECT count(*) FROM measurements").fetchone()[0] == 1
    assert collector.stats == {"stored": 1, "duplicate": 1, "rejected": 2}


# --- Import -----------------------------------------------------------------
def test_import_sample_csv(db_url, db):
    assert import_data.main(["csv", str(SAMPLE_CSV), "--database-url", db_url]) == 0
    count, devices = db.execute("SELECT count(*), count(DISTINCT device_id) FROM measurements").fetchone()
    assert count == 2229 and devices == 1
    # importing again does not create duplicates
    import_data.main(["csv", str(SAMPLE_CSV), "--database-url", db_url])
    assert db.execute("SELECT count(*) FROM measurements").fetchone()[0] == 2229


def test_import_shift_to_now_keeps_time_of_day(db_url, db):
    import_data.main(["csv", str(SAMPLE_CSV), "--database-url", db_url, "--shift-to-now", "--device-id", "TSN-LIVE"])
    first, last = db.execute("SELECT min(measured_at), max(measured_at) FROM measurements").fetchone()
    now = datetime.now(timezone.utc)
    assert now - timedelta(days=1) < last <= now
    assert first.time().replace(microsecond=0) == datetime(2026, 3, 19, 8, 50, 50).time()


# --- API -----------------------------------------------------------------------
@pytest.fixture
def api(db_url):
    with TestClient(create_app(make_settings(db_url))) as client:
        yield client


def seed(db_url, device_id="SIM-001", hours=48, volts_start=12.0, volts_end=11.0, end=None):
    """Write a steadily falling voltage series, one value every 3 min."""
    store = MeasurementStore(db_url)
    end = end or datetime.now(timezone.utc).replace(microsecond=0)
    steps = hours * 20
    for k in range(steps + 1):
        at = end - timedelta(minutes=3 * (steps - k))
        volts = volts_start + (volts_end - volts_start) * k / steps
        topic = build_topic("demo", "trafficnode", device_id)
        store.save(parse_message(topic, msg(at, current_ma=600.0, voltage_mv=volts * 1000)))
    store.close()


def test_health(api):
    assert api.get("/api/health").json() == {"status": "ok", "database": "ok"}


def test_device_list_with_status(api, db_url):
    seed(db_url, "SIM-OK", volts_start=12.6, volts_end=12.4)
    seed(db_url, "SIM-LOW", volts_start=11.8, volts_end=11.4)
    seed(db_url, "SIM-CRIT", volts_start=11.0, volts_end=10.8, end=datetime.now(timezone.utc) - timedelta(hours=5))
    devices = {d["device_id"]: d for d in api.get("/api/devices").json()}
    assert devices["SIM-OK"]["status"] == "ok"
    assert devices["SIM-LOW"]["status"] == "niedrig"
    assert devices["SIM-CRIT"]["status"] == "krit"
    assert devices["SIM-OK"]["stale"] is False
    assert devices["SIM-CRIT"]["stale"] is True
    ok = devices["SIM-OK"]
    # smoothed over the last 60 min, plus shunt correction (0.6 A * 2 mOhm = 1.2 mV)
    assert 12.39 < ok["battery_voltage_v"] < 12.41
    assert ok["position"]["latitude"] == 48.2
    assert ok["current_a"] == 0.6


def test_device_detail_and_trend(api, db_url):
    seed(db_url, "SIM-001", hours=72, volts_start=12.0, volts_end=11.7)
    d = api.get("/api/devices/SIM-001").json()
    assert d["measurement_count"] == 72 * 20 + 1
    assert d["voltage_trend_v_per_day"] == pytest.approx(-0.1, abs=0.005)
    assert d["avg_current_a_24h"] == 0.6


def test_unknown_device_404(api):
    assert api.get("/api/devices/NOPE").status_code == 404
    assert api.get("/api/devices/NOPE/history").status_code == 404


def test_history_buckets_and_range(api, db_url):
    # data ends 30 days ago: default range is relative to the last measurement
    end = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=30)
    seed(db_url, "SIM-001", hours=48, end=end)
    h = api.get("/api/devices/SIM-001/history", params={"hours": 24}).json()
    assert h["bucket_seconds"] == 180
    assert 470 <= len(h["points"]) <= 481
    h7 = api.get("/api/devices/SIM-001/history", params={"hours": 168}).json()
    assert h7["bucket_seconds"] == 1800
    assert len(h7["points"]) in (96, 97, 98)
    p = h7["points"][-1]
    assert p["battery_voltage_min_v"] <= p["battery_voltage_v"] <= p["battery_voltage_max_v"]
    assert 0 <= p["soc_percent"] <= 100


def test_status_rules(api):
    rules = api.get("/api/status-rules").json()
    assert rules["critical_below_percent"] == 20 and rules["low_below_percent"] == 50
    assert rules["shunt_resistance_ohm"] == 0.002


# --- End to end over a real MQTT broker ------------------------------------------
def test_end_to_end_publisher_broker_collector_db(db_url, db):
    host = os.environ.get("TEST_MQTT_HOST")
    if not host:
        pytest.skip("TEST_MQTT_HOST not set")
    port = int(os.environ.get("TEST_MQTT_PORT", "1883"))
    settings = make_settings(db_url, mqtt_host=host, mqtt_port=port, mqtt_client_id=f"bw-test-{time.time_ns()}")
    collector = Collector(settings, MeasurementStore(db_url))
    client = build_client(settings, collector)
    subscribed = threading.Event()
    client.on_subscribe = lambda *a, **k: subscribed.set()
    client.connect(host, port)
    client.loop_start()
    try:
        assert subscribed.wait(10), "collector did not subscribe"
        test_publisher.main(
            ["--host", host, "--port", str(port), "--invalid-every", "4",
             "simulate", "--devices", "3", "--backfill-hours", "0.2", "--once"]
        )
        # 3 devices * (4 backfilled + 1 live) = 15 messages, every 4th broken -> 12 valid
        deadline = time.time() + 10
        while time.time() < deadline and sum(collector.stats.values()) < 15:
            time.sleep(0.1)
    finally:
        client.loop_stop()
        client.disconnect()
    assert collector.stats["rejected"] == 3
    assert db.execute("SELECT count(*) FROM measurements").fetchone()[0] == 12
    assert db.execute("SELECT count(*) FROM devices").fetchone()[0] == 3


# --- Import from a foreign PostgreSQL (history DB) --------------------------------
def test_import_history_detects_columns_and_units(db_url, db):
    db.execute("DROP SCHEMA IF EXISTS src CASCADE")
    db.execute("CREATE SCHEMA src")
    db.execute('CREATE TABLE src.signals ("_time" timestamp, device_id text, tenant text, '
               '"current_A" float8, "voltage_V" float8, latitude float8, longitude float8)')
    db.execute("INSERT INTO src.signals VALUES "
               "('2026-03-19 08:50:50', 'TSN-002', 'dieringer-stark', 0.551, 11.276, 48.2, 8.6), "
               "('2026-03-19 08:53:50', 'TSN-002', 'dieringer-stark', 0.595, 11.304, NULL, NULL), "
               "('2026-03-19 08:56:50', 'TSN-002', 'dieringer-stark', 0.6, 0, NULL, NULL)")
    db.execute("CREATE TABLE src.raw (ts timestamptz, current float8, voltage float8)")
    db.execute("INSERT INTO src.raw VALUES ('2026-03-20 10:00:00+00', 600, 11800)")
    try:
        assert import_data.main(["history", "--source-dsn", db_url, "--table", "src.signals",
                                 "--database-url", db_url]) == 0
        assert import_data.main(["history", "--source-dsn", db_url, "--table", "raw", "--device-id", "OLD-1",
                                 "--database-url", db_url]) == 0
        rows = db.execute("SELECT device_id, measured_at, current_ma, voltage_mv, latitude FROM measurements "
                          "ORDER BY measured_at").fetchall()
    finally:
        db.execute("DROP SCHEMA src CASCADE")
    assert len(rows) == 3  # the 0 V row is skipped
    assert rows[0][0] == "TSN-002"
    assert rows[0][1] == datetime(2026, 3, 19, 8, 50, 50, tzinfo=timezone.utc)  # naive = UTC
    assert rows[0][2] == pytest.approx(551.0) and rows[0][3] == pytest.approx(11276.0)
    assert rows[0][4] == 48.2
    assert rows[2][:1] == ("OLD-1",) and rows[2][2:4] == (600.0, 11800.0)  # unit guessed from values
    assert db.execute("SELECT tenant FROM devices WHERE device_id='TSN-002'").fetchone()[0] == "dieringer-stark"
