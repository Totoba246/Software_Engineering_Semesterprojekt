"""The API: answers the web page's questions with data from the database (ADR-06).

WHAT IS A "REST API"?
    A small web server that returns DATA (JSON) instead of web pages.
    The web page asks e.g.   GET /api/devices
    and gets back            [{"device_id": "101", "soc_percent": 35.2, "status": "niedrig", ...}, ...]

WHERE DOES IT RUN?
    Container "api", port 8000 inside Docker (= port 20801 on the server, only
    reachable from the server itself). The browser doesn't call it directly:
    nginx in the frontend container forwards http://<server>:20800/api/... here.
    Try it on the server:  curl http://127.0.0.1:20801/api/devices
    Clickable documentation of all endpoints: http://127.0.0.1:20801/docs

THE ENDPOINTS (= addresses you can ask), all defined in create_app() below
    GET /api/health                    "are you alive and is the database reachable?"
    GET /api/status-rules              the thresholds (20 %, 50 %, curve) for the legend
    GET /api/devices                   all devices with current battery level and status
    GET /api/devices/101               one device with more details (trend, averages)
    GET /api/devices/101/history       data for the chart (averaged per time slot)
    GET /api/devices/101/messages      the last received MQTT messages, also rejected ones

UNITS
    The database stores mV / mA (like the nodes send). This file converts to
    VOLTS and AMPERES (divide by 1000) because that's easier to read on screen.

It only READS the database; writing is done by the collector.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from .. import battery
from ..config import Settings, get_settings
from ..db import ensure_schema
from . import queries

log = logging.getLogger("batterywatch.api")

# The chart can't draw thousands of points nicely, so measurements are grouped into
# time slots ("buckets") and averaged. Candidate slot sizes in seconds (3 min ... 1 day);
# the smallest one that yields at most MAX_POINTS points is used.
# Example: 7 days = 604800 s / 1800 s = 336 points -> 30-minute slots.
BUCKETS = [180, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400]
MAX_POINTS = 500


# --- Response models ------------------------------------------------------
# These classes describe the exact shape of the JSON answers. FastAPI uses them
# to convert our data to JSON and to generate the documentation at /docs.

class StatusRules(BaseModel):
    critical_below_percent: float
    low_below_percent: float
    soc_curve: list[tuple[float, float]]
    smoothing_minutes: int
    stale_after_minutes: int
    shunt_resistance_ohm: float


class Position(BaseModel):
    latitude: float
    longitude: float
    altitude_m: float | None = None
    satellites: int | None = None


class DeviceSummary(BaseModel):
    """One device in the overview list (answer of GET /api/devices)."""

    device_id: str
    name: str
    tenant: str | None
    device_type: str
    category: str | None
    location: str | None
    last_seen: datetime | None  # time of the newest VALID measurement
    minutes_since_last_seen: float | None
    stale: bool  # True = no valid measurement for STALE_AFTER_MINUTES (shown in red)
    battery_voltage_v: float | None  # smoothed U_bat
    last_battery_voltage_v: float | None  # newest single reading
    current_a: float | None  # newest single reading
    temperature_c: float | None  # newest single reading
    soc_percent: float | None  # charge level 0-100 % (from the smoothed voltage)
    status: battery.BatteryStatus  # "ok" / "niedrig" / "krit" / "unbekannt"
    position: Position | None
    # newest MQTT message, also if it was rejected (e.g. implausible voltage)
    last_message_at: datetime | None
    minutes_since_last_message: float | None
    last_message_error: str | None  # set if the newest message was rejected


class Message(BaseModel):
    """One received MQTT message (answer of GET /api/devices/{id}/messages)."""

    received_at: datetime
    topic: str
    accepted: bool
    error: str | None
    payload: str


class DeviceDetail(DeviceSummary):
    """Everything from DeviceSummary plus extra figures for the detail page."""

    measurement_count: int
    first_seen: datetime | None
    avg_current_a_24h: float | None
    voltage_trend_v_per_day: float | None


class HistoryPoint(BaseModel):
    """One point in the chart = the average of one time slot."""

    t: datetime  # start of the time slot
    battery_voltage_v: float
    battery_voltage_min_v: float
    battery_voltage_max_v: float
    current_a: float
    soc_percent: float
    samples: int  # how many measurements were averaged


class History(BaseModel):
    device_id: str
    start: datetime
    end: datetime
    bucket_seconds: int
    points: list[HistoryPoint]


# --- App setup ------------------------------------------------------------
def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the web application with all its endpoints.

    (A function instead of top-level code so the tests can create an app
    with their own settings, e.g. a separate test database.)
    """
    settings = settings or get_settings()

    # Runs once at start-up (before "yield") and once at shutdown (after it).
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # make sure the tables exist
        with psycopg.connect(settings.database_url, autocommit=True) as conn:
            ensure_schema(conn)
        # A "pool" keeps up to 10 database connections open and lends them to
        # incoming requests - much faster than connecting for every request.
        pool = ConnectionPool(
            settings.database_url, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=True
        )
        app.state.pool = pool
        app.state.settings = settings
        try:
            yield
        finally:
            pool.close()

    app = FastAPI(title="BatteryWatch API", version="0.1.0", lifespan=lifespan)
    # CORS: browser rule about which web pages may call this API. Only relevant
    # in development (page on :5173, API on :8000); in Docker both come via nginx.
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET"], allow_headers=["*"]
    )

    def get_conn(request: Request):
        """Borrow a database connection for one request (given back automatically)."""
        with request.app.state.pool.connection() as conn:
            yield conn

    def summarize(row: dict, now: datetime) -> dict:
        """Turn one database row (mV, mA, timestamps) into the answer for the web page
        (V, A, minutes ago, percentage and status)."""
        s: Settings = settings
        avg_mv = row["avg_battery_voltage_mv"]  # average of the last 60 min, in mV
        volts = round(avg_mv / 1000, 3) if avg_mv is not None else None  # mV -> V
        soc = battery.state_of_charge(volts, s.soc_curve)  # V -> %
        last_seen = row["last_seen"]
        minutes = (now - last_seen).total_seconds() / 60 if last_seen else None
        last_msg = row["last_message_at"]
        msg_minutes = (now - last_msg).total_seconds() / 60 if last_msg else None
        position = None
        if row["latitude"] is not None:
            position = Position(
                latitude=row["latitude"],
                longitude=row["longitude"],
                altitude_m=row["altitude_m"],
                satellites=row["satellites"],
            )
        return dict(
            device_id=row["device_id"],
            name=row["name"] or row["device_id"],
            tenant=row["tenant"],
            device_type=row["device_type"],
            category=row["category"],
            location=row["location"],
            last_seen=last_seen,
            minutes_since_last_seen=round(minutes, 1) if minutes is not None else None,
            stale=minutes is None or minutes > s.stale_after_minutes,
            battery_voltage_v=volts,
            last_battery_voltage_v=(
                round(row["last_battery_voltage_mv"] / 1000, 3) if row["last_battery_voltage_mv"] is not None else None
            ),
            current_a=round(row["last_current_ma"] / 1000, 3) if row["last_current_ma"] is not None else None,
            temperature_c=round(row["temperature_c"], 1) if row["temperature_c"] is not None else None,
            last_message_at=last_msg,
            minutes_since_last_message=round(msg_minutes, 1) if msg_minutes is not None else None,
            last_message_error=row["last_message_error"] if row["last_message_accepted"] is False else None,
            soc_percent=round(soc, 1) if soc is not None else None,
            status=battery.classify(soc, s.status_critical_below, s.status_low_below),
            position=position,
        )

    def fetch_states(conn, device_id: str | None = None) -> list[dict]:
        """Current state of all devices, or of one device if ``device_id`` is given."""
        where = "WHERE d.device_id = %(device_id)s" if device_id else ""
        rows = conn.execute(
            queries.DEVICE_STATE.format(where=where),
            {"window_minutes": settings.smoothing_minutes, "device_id": device_id},
        ).fetchall()
        now = datetime.now(timezone.utc)
        return [summarize(r, now) for r in rows]

    # --- Routes -----------------------------------------------------------
    # "@app.get(path)" = "when someone requests this address, run this function".
    # "{device_id}" in the path is filled from the address, e.g. /api/devices/101.
    # "conn=Depends(get_conn)" = FastAPI hands the function a database connection.

    @app.get("/api/health")
    def health(conn=Depends(get_conn)):
        conn.execute("SELECT 1")
        return {"status": "ok", "database": "ok"}

    @app.get("/api/status-rules", response_model=StatusRules)
    def status_rules():
        return StatusRules(
            critical_below_percent=settings.status_critical_below,
            low_below_percent=settings.status_low_below,
            soc_curve=settings.soc_curve,
            smoothing_minutes=settings.smoothing_minutes,
            stale_after_minutes=settings.stale_after_minutes,
            shunt_resistance_ohm=settings.shunt_resistance_ohm,
        )

    @app.get("/api/devices", response_model=list[DeviceSummary])
    def list_devices(conn=Depends(get_conn)):
        return fetch_states(conn)

    @app.get("/api/devices/{device_id}", response_model=DeviceDetail)
    def get_device(device_id: str, conn=Depends(get_conn)):
        states = fetch_states(conn, device_id)
        if not states:
            raise HTTPException(status_code=404, detail="Gerät nicht gefunden")
        state = states[0]
        stats = {"measurement_count": 0, "first_seen": None, "avg_current_ma_24h": None, "trend_v_per_day": None}
        if state["last_seen"] is not None:
            stats = conn.execute(
                queries.DEVICE_STATS, {"device_id": device_id, "last_seen": state["last_seen"]}
            ).fetchone()
        return DeviceDetail(
            **state,
            measurement_count=stats["measurement_count"],
            first_seen=stats["first_seen"],
            avg_current_a_24h=(
                round(stats["avg_current_ma_24h"] / 1000, 3) if stats["avg_current_ma_24h"] is not None else None
            ),
            voltage_trend_v_per_day=(
                round(stats["trend_v_per_day"], 3) if stats["trend_v_per_day"] is not None else None
            ),
        )

    @app.get("/api/devices/{device_id}/history", response_model=History)
    def get_history(
        # e.g. /api/devices/101/history?hours=168  (168 h = 7 days)
        device_id: str,
        hours: int = Query(168, ge=1, le=24 * 365, description="Length of the time range in hours"),
        end: datetime | None = Query(None, description="End of the range; default = last measurement"),
        conn=Depends(get_conn),
    ):
        # The time range ends at the device's NEWEST measurement (not "now"), so
        # old/imported data still shows a chart instead of an empty one.
        if end is None:
            row = conn.execute(queries.LAST_SEEN, {"device_id": device_id}).fetchone()
            if row["last_seen"] is None:
                exists = conn.execute("SELECT 1 FROM devices WHERE device_id = %s", (device_id,)).fetchone()
                if not exists:
                    raise HTTPException(status_code=404, detail="Gerät nicht gefunden")
                end = datetime.now(timezone.utc)
            else:
                end = row["last_seen"]
        elif end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        start = end - timedelta(hours=hours)
        # pick the time slot size (see BUCKETS at the top)
        bucket = next((b for b in BUCKETS if hours * 3600 / b <= MAX_POINTS), BUCKETS[-1])
        rows = conn.execute(
            queries.HISTORY, {"device_id": device_id, "bucket_seconds": bucket, "start": start, "end": end}
        ).fetchall()
        points = [
            HistoryPoint(
                t=r["t"],
                battery_voltage_v=round(r["avg_mv"] / 1000, 3),
                battery_voltage_min_v=round(r["min_mv"] / 1000, 3),
                battery_voltage_max_v=round(r["max_mv"] / 1000, 3),
                current_a=round(r["avg_ma"] / 1000, 3),
                soc_percent=round(battery.state_of_charge(r["avg_mv"] / 1000, settings.soc_curve), 1),
                samples=r["n"],
            )
            for r in rows
        ]
        return History(device_id=device_id, start=start, end=end, bucket_seconds=bucket, points=points)

    @app.get("/api/devices/{device_id}/messages", response_model=list[Message])
    def get_messages(device_id: str, limit: int = Query(20, ge=1, le=500), conn=Depends(get_conn)):
        """Newest received MQTT messages of a device, including rejected ones."""
        if not conn.execute("SELECT 1 FROM devices WHERE device_id = %s", (device_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Gerät nicht gefunden")
        return conn.execute(queries.MESSAGES, {"device_id": device_id, "limit": limit}).fetchall()

    return app


# The object the web server "uvicorn" runs (see the CMD in backend/Dockerfile:
# "uvicorn batterywatch.api.main:app" = file batterywatch/api/main.py, variable app).
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
