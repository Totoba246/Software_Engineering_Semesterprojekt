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
TEST_PASSWORD = "geheim123"


@pytest.fixture
def db_url(monkeypatch) -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    monkeypatch.setenv("DATABASE_URL", url)
    with psycopg.connect(url, autocommit=True) as conn:
        ensure_schema(conn)
        conn.execute("TRUNCATE appointments, measurements, devices, raw_messages, sessions, users RESTART IDENTITY CASCADE")
    return url


@pytest.fixture
def db(db_url):
    with psycopg.connect(db_url, autocommit=True) as conn:
        yield conn


@pytest.fixture
def make_client(db_url):
    """Factory for API test clients: make_client("techniker", "elif") creates that
    user (password TEST_PASSWORD) and returns a client that is logged in as them.
    make_client() without a role returns a client that is not logged in."""
    from fastapi.testclient import TestClient

    from batterywatch.api.main import create_app
    from batterywatch.config import Settings
    from batterywatch.tools.manage import create_user

    clients = []

    def make(role: str | None = None, username: str | None = None, must_change: bool = False):
        client = TestClient(create_app(Settings(database_url=db_url)))
        client.__enter__()  # runs the app's start-up (database pool)
        clients.append(client)
        if role:
            username = username or role
            with psycopg.connect(db_url, autocommit=True) as conn:
                create_user(conn, username, username.title(), role, TEST_PASSWORD, must_change=must_change)
            response = client.post("/api/auth/login", json={"username": username, "password": TEST_PASSWORD})
            assert response.status_code == 200, response.text
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def user_id(db, username: str) -> int:
    return db.execute("SELECT id FROM users WHERE username = %s", (username,)).fetchone()[0]
