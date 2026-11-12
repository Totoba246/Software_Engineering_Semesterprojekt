"""Writing into our PostgreSQL database.

WHAT THIS FILE DOES
    - ``ensure_schema``: creates the tables if they don't exist yet (on every start).
    - ``MeasurementStore``: saves measurements and the message log.
      Before saving, it calculates the real battery voltage
      (U_bat = 0.002 Ohm * I + U_measured, see battery.py).

WHO USES IT
    - collector/main.py  -> ``save_message`` for every MQTT message
    - tools/import_data.py and the test publisher -> ``save_many`` for bulk imports
    - api/main.py only uses ``ensure_schema`` (it reads with its own SQL, api/queries.py)

WHERE IS THE DATABASE?
    Given by DATABASE_URL (see config.py). In Docker: container "db", port 5432
    inside Docker (= port 20832 on the server).

SQL IN 30 SECONDS
    INSERT INTO table (columns) VALUES (...)  -> add a row
    ON CONFLICT (...) DO NOTHING              -> if that row already exists, skip it
    %s                                        -> placeholder; psycopg fills in the values
                                                 safely (never glue values into SQL text!)
"""

from __future__ import annotations

import logging
import time
from importlib import resources
from typing import Iterable

import psycopg

from .battery import battery_voltage_mv
from .contract import Measurement, TopicInfo

log = logging.getLogger(__name__)

# Register a device the first time we hear from it; if it exists already, do nothing.
_UPSERT_DEVICE = """
    INSERT INTO devices (device_id, tenant, device_type)
    VALUES (%s, %s, %s)
    ON CONFLICT (device_id) DO NOTHING
"""

# The columns of the measurements table we fill (see schema.sql for their meaning).
_COLUMNS = ("device_id, measured_at, current_ma, voltage_mv, battery_voltage_mv, "
            "latitude, longitude, altitude_m, satellites, temperature_c, source")

# Save one measurement. The same device + same timestamp twice (e.g. a message
# delivered twice, or an import run twice) is silently skipped.
_INSERT_MEASUREMENT = f"""
    INSERT INTO measurements ({_COLUMNS})
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (device_id, measured_at) DO NOTHING
"""

# Log one received MQTT message, valid or not (table raw_messages).
_INSERT_RAW = """
    INSERT INTO raw_messages (topic, device_id, payload, accepted, error)
    VALUES (%s, %s, %s, %s, %s)
"""


def schema_sql() -> str:
    """The text of schema.sql (the file with all CREATE TABLE commands)."""
    return resources.files("batterywatch").joinpath("schema.sql").read_text(encoding="utf-8")


def ensure_schema(conn: psycopg.Connection) -> None:
    """Create/upgrade the tables. Safe to run any number of times."""
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
    """One measurement as a tuple of values, in the order of _COLUMNS."""
    return (
        m.device_id,
        m.measured_at,
        m.current_ma,
        m.voltage_mv,
        battery_voltage_mv(m.voltage_mv, m.current_ma, shunt_resistance_ohm),  # U_bat in mV
        m.latitude,
        m.longitude,
        m.altitude_m,
        m.satellites,
        m.temperature_c,
        source,  # "mqtt" (live) or "import" (imported/simulated history)
    )


class MeasurementStore:
    """Writes validated measurements. Reconnects once if the connection was lost.

    Keeps ONE open connection to the database and reuses it for every message
    (opening a new connection each time would be slow).
    """

    def __init__(self, database_url: str, shunt_resistance_ohm: float = 0.002):
        self._url = database_url
        self._shunt = shunt_resistance_ohm
        self._conn: psycopg.Connection | None = None

    @property
    def conn(self) -> psycopg.Connection:
        """The open database connection; (re)connects if there is none."""
        if self._conn is None or self._conn.closed:
            self._conn = connect_with_retry(self._url)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()

    def save(self, m: Measurement, source: str = "mqtt") -> bool:
        """Store one measurement. Returns False if it was a duplicate."""
        return self._with_retry(lambda conn: self._insert(conn, m, source))

    def save_message(
        self,
        topic: str,
        payload: str,
        device: TopicInfo | None,
        measurement: Measurement | None,
        error: str | None,
    ) -> bool:
        """Log a received MQTT message and, if it was valid, store its measurement.

        The device is registered as soon as the topic is valid, so a node that
        only sends implausible values still shows up (with the reason).
        Returns False if the measurement was a duplicate.
        """

        def work(conn: psycopg.Connection) -> bool:
            # 1. topic was fine -> make sure the device exists (even if the values are bad)
            if device is not None:
                conn.execute(_UPSERT_DEVICE, (device.device_id, device.tenant, device.device_type))
            # 2. always log the message itself (cut to 4000 characters, just in case)
            conn.execute(_INSERT_RAW, (topic, device.device_id if device else None, payload[:4000],
                                       measurement is not None, error))
            # 3. only VALID messages become a measurement
            return self._insert(conn, measurement, "mqtt") if measurement is not None else False

        return self._with_retry(work)

    def _insert(self, conn: psycopg.Connection, m: Measurement, source: str) -> bool:
        """Save one measurement; True if new, False if it already existed."""
        conn.execute(_UPSERT_DEVICE, (m.device_id, m.tenant, m.device_type))
        return conn.execute(_INSERT_MEASUREMENT, _row(m, self._shunt, source)).rowcount == 1

    def _with_retry(self, work):
        """Run ``work`` in one transaction (all or nothing). If the database
        connection was lost (e.g. the db container restarted), reconnect and
        try exactly once more."""
        for attempt in (1, 2):
            try:
                with self.conn.transaction():
                    return work(self.conn)
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
        """Fast path for thousands of rows: COPY them into a temporary table in
        one go, then move them into measurements while skipping duplicates."""
        conn = self.conn
        with conn.transaction():
            devices = {(m.device_id, m.tenant, m.device_type) for m in batch}
            with conn.cursor() as cur:
                # sort by device id only: tenant may be None, which can't be compared with text
                cur.executemany(_UPSERT_DEVICE, sorted(devices, key=lambda d: d[0]))
            conn.execute(
                "CREATE TEMP TABLE IF NOT EXISTS import_buffer (device_id TEXT, measured_at TIMESTAMPTZ, "
                "current_ma FLOAT8, voltage_mv FLOAT8, battery_voltage_mv FLOAT8, latitude FLOAT8, "
                "longitude FLOAT8, altitude_m FLOAT8, satellites INTEGER, temperature_c FLOAT8, source TEXT) "
                "ON COMMIT DELETE ROWS"
            )
            with conn.cursor() as cur:
                with cur.copy(f"COPY import_buffer ({_COLUMNS}) FROM STDIN") as copy:
                    for m in batch:
                        copy.write_row(_row(m, self._shunt, source))
            cur = conn.execute(
                f"INSERT INTO measurements ({_COLUMNS}) "
                f"SELECT DISTINCT ON (device_id, measured_at) {_COLUMNS} FROM import_buffer "
                "ON CONFLICT (device_id, measured_at) DO NOTHING"
            )
            return cur.rowcount
