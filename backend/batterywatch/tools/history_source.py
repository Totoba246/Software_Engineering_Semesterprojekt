"""Read measurements from another PostgreSQL database whose layout we don't control
(e.g. the course's history database), by guessing which columns mean what.

The guess is based on column names (``_time``, ``voltage_V``, ``current_mA``, ...)
and, where the name has no unit, on the size of the values (11.3 -> volts, 11300 -> mV).
If no table fits, ``describe()`` prints the layout so the mapping can be given by hand
via ``import_data sql --query ...``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import psycopg
from psycopg import sql

log = logging.getLogger("batterywatch.import")

# candidate column names (lower case), best first
TIME_NAMES = ["measured_at", "_time", "time", "timestamp", "ts", "datetime", "recorded_at", "created_at", "received_at"]
DEVICE_NAMES = ["device_id", "deviceid", "device", "node_id", "node", "serial"]
CURRENT = {"current_ma": 1.0, "current_a": 1000.0, "i_ma": 1.0, "i_a": 1000.0, "current": None, "strom": None}
VOLTAGE = {"voltage_mv": 1.0, "voltage_v": 1000.0, "u_mv": 1.0, "u_v": 1000.0, "voltage": None, "spannung": None}
OPTIONAL = {
    "latitude": ["latitude", "lat"],
    "longitude": ["longitude", "lon", "lng"],
    "altitude_m": ["altitude_m", "altitude", "alt"],
    "satellites": ["satellites", "sats", "satellite_count"],
    "tenant": ["tenant", "operator"],
    "device_type": ["device_type", "type"],
}


@dataclass
class Mapping:
    schema: str
    table: str
    time: str
    current: str
    voltage: str
    current_factor: float | None  # multiply to get mA (None = decide from the data)
    voltage_factor: float | None  # multiply to get mV
    device: str | None = None
    optional: dict[str, str] = field(default_factory=dict)

    def describe(self) -> str:
        parts = [f"time={self.time}", f"device={self.device or '(fixed)'}",
                 f"current={self.current} x{self.current_factor}", f"voltage={self.voltage} x{self.voltage_factor}"]
        parts += [f"{k}={v}" for k, v in self.optional.items()]
        return f"{self.schema}.{self.table}: " + ", ".join(parts)


def list_tables(conn: psycopg.Connection) -> dict[tuple[str, str], list[tuple[str, str]]]:
    rows = conn.execute(
        """
        SELECT c.table_schema, c.table_name, c.column_name, c.data_type
        FROM information_schema.columns c
        JOIN information_schema.tables t USING (table_schema, table_name)
        WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
          AND t.table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY c.table_schema, c.table_name, c.ordinal_position
        """
    ).fetchall()
    tables: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for schema, table, column, dtype in rows:
        tables.setdefault((schema, table), []).append((column, dtype))
    return tables


def describe(conn: psycopg.Connection) -> str:
    lines = []
    for (schema, table), cols in list_tables(conn).items():
        count = conn.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(sql.Identifier(schema), sql.Identifier(table))
        ).fetchone()[0]
        lines.append(f"{schema}.{table}  ({count} rows)")
        lines += [f"    {c}  {t}" for c, t in cols]
    return "\n".join(lines) or "(no tables visible for this user)"


def _pick(columns: dict[str, str], names) -> str | None:
    for name in names:
        if name in columns:
            return columns[name]
    return None


def guess_mapping(tables: dict[tuple[str, str], list[tuple[str, str]]], table: str | None = None) -> Mapping | None:
    best: tuple[int, Mapping] | None = None
    for (schema, tname), cols in tables.items():
        if table and table not in (tname, f"{schema}.{tname}"):
            continue
        by_lower = {c.lower(): c for c, _ in cols}
        time_col = _pick(by_lower, TIME_NAMES)
        cur = next(((by_lower[n], f) for n, f in CURRENT.items() if n in by_lower), None)
        volt = next(((by_lower[n], f) for n, f in VOLTAGE.items() if n in by_lower), None)
        if not (time_col and cur and volt):
            continue
        m = Mapping(schema, tname, time_col, cur[0], volt[0], cur[1], volt[1], device=_pick(by_lower, DEVICE_NAMES))
        for target, names in OPTIONAL.items():
            col = _pick(by_lower, names)
            if col:
                m.optional[target] = col
        score = 10 + (5 if m.device else 0) + len(m.optional)
        if best is None or score > best[0]:
            best = (score, m)
    return best[1] if best else None


def _resolve_units(conn: psycopg.Connection, m: Mapping) -> None:
    """For columns without a unit in the name, decide from typical values."""
    if m.current_factor is not None and m.voltage_factor is not None:
        return
    q = sql.SQL("SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY abs({c}::float8)), "
                "percentile_cont(0.5) WITHIN GROUP (ORDER BY {v}::float8) FROM {s}.{t} WHERE {v}::float8 > 0").format(
        c=sql.Identifier(m.current), v=sql.Identifier(m.voltage), s=sql.Identifier(m.schema), t=sql.Identifier(m.table))
    med_current, med_voltage = conn.execute(q).fetchone()
    if m.voltage_factor is None:
        # a 12 V battery: ~11-13 in volts, ~11000-13000 in millivolts
        m.voltage_factor = 1.0 if (med_voltage or 0) > 100 else 1000.0
    if m.current_factor is None:
        # the node draws ~0.5-0.7 A: < 20 means amperes
        m.current_factor = 1.0 if (med_current or 0) > 20 else 1000.0


def build_query(m: Mapping, device_id: str | None) -> sql.Composed:
    def col(name: str) -> sql.Identifier:
        return sql.Identifier(name)

    fields = [
        sql.SQL("{}::text AS device_id").format(col(m.device)) if m.device and not device_id
        else sql.SQL("{}::text AS device_id").format(sql.Literal(device_id or "unknown")),
        sql.SQL("{}::timestamptz AS measured_at").format(col(m.time)),
        sql.SQL("{}::float8 * {} AS current_ma").format(col(m.current), sql.Literal(m.current_factor)),
        sql.SQL("{}::float8 * {} AS voltage_mv").format(col(m.voltage), sql.Literal(m.voltage_factor)),
    ]
    casts = {"latitude": "float8", "longitude": "float8", "altitude_m": "float8", "satellites": "int",
             "tenant": "text", "device_type": "text"}
    for target, source in m.optional.items():
        fields.append(sql.SQL("{}::{} AS {}").format(col(source), sql.SQL(casts[target]), col(target)))
    return sql.SQL("SELECT {} FROM {}.{} WHERE {} IS NOT NULL AND {} IS NOT NULL AND {} IS NOT NULL ORDER BY 2").format(
        sql.SQL(", ").join(fields), col(m.schema), col(m.table), col(m.time), col(m.current), col(m.voltage))


def auto_query(dsn: str, table: str | None, device_id: str | None) -> str:
    """Return a ready SQL query for ``import_data sql``, or raise SystemExit with the layout."""
    with psycopg.connect(dsn) as conn:
        conn.execute("SET TIME ZONE 'UTC'")  # timestamps without zone are UTC
        m = guess_mapping(list_tables(conn), table)
        if m is None:
            raise SystemExit(
                "Could not find a table with time, current and voltage columns.\n"
                "Database layout:\n" + describe(conn) +
                "\n\nUse `import_data sql --query ...` with explicit column aliases (see docs/Entwicklung.md)."
            )
        if not m.device and not device_id:
            log.warning("no device column found, storing everything as device 'unknown' (use --device-id)")
        _resolve_units(conn, m)
        log.info("using %s", m.describe())
        return build_query(m, device_id).as_string(conn)
