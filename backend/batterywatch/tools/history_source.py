"""Read measurements from another PostgreSQL database whose layout we don't control
(e.g. the course's history database), by guessing which columns mean what.

WHERE IS THAT DATABASE?
    The course's history PostgreSQL runs on the course server itself at
    127.0.0.1:5432 (database "measurements"). It is only reachable from the
    server, so deploy/import-history.sh runs the import ON the server.
    We only READ from it, never write.

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
    topic: str | None = None      # MQTT topic column, used for the device id if there is no device column
    optional: dict[str, str] = field(default_factory=dict)
    rows: int | None = None       # number of usable rows (filled in by auto_query)

    def describe(self) -> str:
        device = self.device or (f"from topic column {self.topic}" if self.topic else "(fixed)")
        parts = [f"rows={self.rows}", f"time={self.time}", f"device={device}",
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
    """The best-fitting table by column names alone (see ``candidates``)."""
    found = candidates(tables, table)
    return found[0] if found else None


def candidates(tables: dict[tuple[str, str], list[tuple[str, str]]], table: str | None = None) -> list[Mapping]:
    """All tables that have time, current and voltage columns, best fit first."""
    scored: list[tuple[int, Mapping]] = []
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
        if not m.device:
            m.topic = by_lower.get("topic")
        for target, names in OPTIONAL.items():
            col = _pick(by_lower, names)
            if col:
                m.optional[target] = col
        score = 10 + (5 if m.device else 4 if m.topic else 0) + len(m.optional)
        scored.append((score, m))
    scored.sort(key=lambda sm: -sm[0])  # stable: equal scores keep database order
    return [m for _, m in scored]


def _resolve_units(conn: psycopg.Connection, m: Mapping) -> None:
    """For columns without a unit in the name, decide from typical values.

    Counts how many values look like volts (5-20) vs millivolts (5000-20000)
    and amperes (0.05-5) vs milliamperes (50-5000). Counting instead of taking
    the median keeps the decision right even if many values are garbage
    (e.g. 5368709120).
    """
    if m.current_factor is not None and m.voltage_factor is not None:
        return
    q = sql.SQL(
        "SELECT count(*) FILTER (WHERE {v}::float8 BETWEEN 5 AND 20), "
        "       count(*) FILTER (WHERE {v}::float8 BETWEEN 5000 AND 20000), "
        "       count(*) FILTER (WHERE abs({c}::float8) BETWEEN 0.05 AND 5), "
        "       count(*) FILTER (WHERE abs({c}::float8) BETWEEN 50 AND 5000) "
        "FROM {s}.{t}"
    ).format(c=sql.Identifier(m.current), v=sql.Identifier(m.voltage), s=sql.Identifier(m.schema),
             t=sql.Identifier(m.table))
    volts, millivolts, amps, milliamps = conn.execute(q).fetchone()
    if m.voltage_factor is None:
        m.voltage_factor = 1000.0 if volts > millivolts else 1.0  # volts -> x1000 to get mV
    if m.current_factor is None:
        m.current_factor = 1000.0 if amps > milliamps else 1.0


def build_query(m: Mapping, device_id: str | None) -> sql.Composed:
    def col(name: str) -> sql.Identifier:
        return sql.Identifier(name)

    if device_id:                       # given by hand (--device-id)
        device = sql.SQL("{}::text").format(sql.Literal(device_id))
    elif m.device:                      # a device column
        device = sql.SQL("{}::text").format(col(m.device))
    elif m.topic:                       # from the MQTT topic: traffic-nodes/<id>/measurements
        device = sql.SQL(                # or traffic-device/<tenant>/<type>/<id>/status
            "CASE WHEN split_part({t}, '/', 1) = 'traffic-device' THEN split_part({t}, '/', 4) "
            "ELSE split_part({t}, '/', 2) END").format(t=col(m.topic))
    else:
        device = sql.SQL("'unknown'::text")
    fields = [
        sql.SQL("{} AS device_id").format(device),
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
        found = candidates(list_tables(conn), table)
        # Several tables may fit by name (e.g. an empty template table). Count the
        # usable rows of each and take the best fit that actually contains data.
        for c in found:
            c.rows = conn.execute(sql.SQL(
                "SELECT count(*) FROM {}.{} WHERE {} IS NOT NULL AND {} IS NOT NULL AND {} IS NOT NULL").format(
                sql.Identifier(c.schema), sql.Identifier(c.table), sql.Identifier(c.time),
                sql.Identifier(c.current), sql.Identifier(c.voltage))).fetchone()[0]
            log.info("candidate table %s.%s: %d usable rows", c.schema, c.table, c.rows)
        m = next((c for c in found if c.rows), None)
        if m is None:
            reason = ("Keine Tabelle mit Zeit-, Strom- und Spannungsspalten gefunden." if not found else
                      "Die passenden Tabellen sind alle LEER (0 Zeilen).")
            raise SystemExit(
                f"\n{reason}\nSo sieht die Datenbank aus (Tabellen, Zeilenzahl, Spalten):\n\n" + describe(conn) +
                "\n\n-> Bitte diese Ausgabe an Claude/das Team schicken, dann wird die Zuordnung angepasst."
            )
        if not m.device and not m.topic and not device_id:
            log.warning("no device column found, storing everything as device 'unknown' (use --device-id)")
        _resolve_units(conn, m)
        log.info("using %s", m.describe())
        return build_query(m, device_id).as_string(conn)
