"""Shared fixtures.

Integration tests need a PostgreSQL database and are skipped unless
TEST_DATABASE_URL is set, e.g.::

    TEST_DATABASE_URL=postgresql://batterywatch:batterywatch@localhost:5432/batterywatch_test pytest

The MQTT end-to-end test additionally needs TEST_MQTT_HOST (and optionally TEST_MQTT_PORT).
WARNING: the test database is wiped by the tests - never point it at real data.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

from batterywatch.db import ensure_schema

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_CSV = REPO_ROOT / "docs" / "samples" / "traffic_devices_signals.csv"


@pytest.fixture
def db_url(monkeypatch) -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    monkeypatch.setenv("DATABASE_URL", url)
    with psycopg.connect(url, autocommit=True) as conn:
        ensure_schema(conn)
        conn.execute("TRUNCATE measurements, devices RESTART IDENTITY CASCADE")
    return url


@pytest.fixture
def db(db_url):
    with psycopg.connect(db_url, autocommit=True) as conn:
        yield conn
