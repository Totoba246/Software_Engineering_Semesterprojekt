"""Database access shared by the collector, the import tool and the API."""

from __future__ import annotations

import logging
import time
from importlib import resources
from typing import Iterable

import psycopg

from .battery import battery_voltage_mv
from .contract import Measurement

log = logging.getLogger(__name__)

_UPSERT_DEVICE = """
    INSERT INTO devices (device_id, tenant, device_type)
    VALUES (%s, %s, %s)
    ON CONFLICT (device_id) DO NOTHING
"""

_INSERT_MEASUREMENT = """
    INSERT INTO measurements (device_id, measured_at, current_ma, voltage_mv, battery_voltage_mv,
                              latitude, longitude, altitude_m, satellites, source)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (device_id, measured_at) DO NOTHING
"""


def schema_sql() -> str:
    return resources.files("batterywatch").joinpath("schema.sql").read_text(encoding="utf-8")


def ensure_schema(conn: psycopg.Connection) -> None:
    with conn.transaction():
        # Serialise concurrent startups (API and collector start at the same time).
        conn.execute("SELECT pg_advisory_xact_lock(4711)")
        conn.execute(schema_sql())


def connect_with_retry(database_url: str, attempts: int = 30, delay_s: float = 2.0) -> psycopg.Connection:
    """Connect to PostgreSQL, waiting for the container to come up if necessary."""
    for attempt in range(1, attempts + 1):
        try:
            return psycopg.connect(database_url, autocommit=True)
        except psycopg.OperationalError as exc:
            if attempt == attempts:
                raise
            log.warning("database not reachable (%s), retry %d/%d in %.0fs", exc, attempt, attempts, delay_s)
            time.sleep(delay_s)
    raise AssertionError("unreachable")


def _row(m: Measurement, shunt_resistance_ohm: float, source: str) -> tuple:
    return (
        m.device_id,
        m.measured_at,
        m.current_ma,
        m.voltage_mv,
        battery_voltage_mv(m.voltage_mv, m.current_ma, shunt_resistance_ohm),
        m.latitude,
        m.longitude,
        m.altitude_m,
        m.satellites,
        source,
    )


class MeasurementStore:
    """Writes validated measurements. Reconnects once if the connection was lost."""

    def __init__(self, database_url: str, shunt_resistance_ohm: float = 0.002):
        self._url = database_url
        self._shunt = shunt_resistance_ohm
        self._conn: psycopg.Connection | None = None

    @property
    def conn(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = connect_with_retry(self._url)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()

    def save(self, m: Measurement, source: str = "mqtt") -> bool:
        """Store one measurement. Returns False if it was a duplicate."""
        for attempt in (1, 2):
            try:
                with self.conn.transaction():
                    self.conn.execute(_UPSERT_DEVICE, (m.device_id, m.tenant, m.device_type))
                    cur = self.conn.execute(_INSERT_MEASUREMENT, _row(m, self._shunt, source))
                    return cur.rowcount == 1
            except psycopg.OperationalError:
                if attempt == 2:
                    raise
                log.warning("database connection lost, reconnecting")
                self._conn = None
        raise AssertionError("unreachable")

    def save_many(self, measurements: Iterable[Measurement], source: str = "import", batch_size: int = 5000) -> int:
        """Bulk insert (used by the import tool). Returns the number of new rows."""
        inserted = 0
        batch: list[Measurement] = []
        for m in measurements:
            batch.append(m)
            if len(batch) >= batch_size:
                inserted += self._save_batch(batch, source)
                batch = []
        if batch:
            inserted += self._save_batch(batch, source)
        return inserted

    def _save_batch(self, batch: list[Measurement], source: str) -> int:
        conn = self.conn
        with conn.transaction():
            devices = {(m.device_id, m.tenant, m.device_type) for m in batch}
            with conn.cursor() as cur:
                cur.executemany(_UPSERT_DEVICE, sorted(devices))
            conn.execute(
                "CREATE TEMP TABLE IF NOT EXISTS import_buffer (device_id TEXT, measured_at TIMESTAMPTZ, "
                "current_ma FLOAT8, voltage_mv FLOAT8, battery_voltage_mv FLOAT8, latitude FLOAT8, "
                "longitude FLOAT8, altitude_m FLOAT8, satellites INTEGER, source TEXT) ON COMMIT DELETE ROWS"
            )
            with conn.cursor() as cur:
                with cur.copy(
                    "COPY import_buffer (device_id, measured_at, current_ma, voltage_mv, battery_voltage_mv, "
                    "latitude, longitude, altitude_m, satellites, source) FROM STDIN"
                ) as copy:
                    for m in batch:
                        copy.write_row(_row(m, self._shunt, source))
            cur = conn.execute(
                "INSERT INTO measurements (device_id, measured_at, current_ma, voltage_mv, battery_voltage_mv, "
                "latitude, longitude, altitude_m, satellites, source) "
                "SELECT DISTINCT ON (device_id, measured_at) device_id, measured_at, current_ma, voltage_mv, "
                "battery_voltage_mv, latitude, longitude, altitude_m, satellites, source FROM import_buffer "
                "ON CONFLICT (device_id, measured_at) DO NOTHING"
            )
            return cur.rowcount
