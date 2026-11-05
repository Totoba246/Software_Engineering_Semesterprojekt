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
# if the chosen time column is empty in a row, use this one instead (e.g. measured_at -> received_at;
# node 101 sends "time": null, so only the server's receive time exists)
TIME_FALLBACK_NAMES = ["received_at", "created_at", "inserted_at"]
# explicit device columns; if none exists, the id comes from the MQTT topic, then from a serial number
DEVICE_NAMES = ["device_id", "deviceid", "device", "node_id", "node"]
SERIAL_NAMES = ["serial_number", "serial"]
CURRENT = {"current_ma": 1.0, "current_a": 1000.0, "i_ma": 1.0, "i_a": 1000.0, "current": None, "strom": None}
VOLTAGE = {"voltage_mv": 1.0, "voltage_v": 1000.0, "u_mv": 1.0, "u_v": 1000.0, "voltage": None, "spannung": None}
# JSON column with the original message; its keys follow the MQTT contract (mA / mV)
PAYLOAD_NAMES = ["payload", "message", "body", "data"]
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
    """Which column of the source table means what."""

    schema: str
    table: str
    time: str
    current: str
    voltage: str
    current_factor: float | None  # multiply to get mA (None = decide from the data)
    voltage_factor: float | None  # multiply to get mV
    device: str | None = None
    topic: str | None = None        # MQTT topic column -> device id if there is no device column
    serial: str | None = None       # serial number column -> device id as last resort
    time_fallback: str | None = None  # used where `time` is NULL
    payload: str | None = None      # jsonb with the original message, used where current/voltage are NULL
    optional: dict[str, str] = field(default_factory=dict)
    rows: int | None = None         # number of usable rows (filled in by auto_query)

    def describe(self) -> str:
        if self.device:
            device = self.device
        elif self.topic:
            device = f"from topic column {self.topic}" + (f" (else {self.serial})" if self.serial else "")
        else:
            device = self.serial or "(fixed)"
        time = self.time + (f" (else {self.time_fallback})" if self.time_fallback else "")
        extra = f" (else {self.payload} JSON)" if self.payload else ""
        parts = [f"rows={self.rows}", f"time={time}", f"device={device}",
                 f"current={self.current} x{self.current_factor}{extra}",
                 f"voltage={self.voltage} x{self.voltage_factor}{extra}"]
        parts += [f"{k}={v}" for k, v in self.optional.items()]
        return f"{self.schema}.{self.table}: " + ", ".join(parts)

    # --- SQL expressions (each falls back to the next source if NULL) ------
    def time_sql(self) -> sql.Composable:
        expr = sql.SQL("{}::timestamptz").format(sql.Identifier(self.time))
        if self.time_fallback:
            expr = sql.SQL("COALESCE({}, {}::timestamptz)").format(expr, sql.Identifier(self.time_fallback))
        return expr

    def _value_sql(self, column: str, factor: float | None, payload_key: str) -> sql.Composable:
        expr = sql.SQL("{}::float8 * {}").format(sql.Identifier(column), sql.Literal(factor or 1.0))
        if self.payload:
            # only take JSON numbers, so a broken value can't make the whole query fail
            p = sql.Identifier(self.payload)
            expr = sql.SQL("COALESCE({e}, CASE WHEN jsonb_typeof({p}::jsonb -> {k}) = 'number' "
                           "THEN ({p}::jsonb ->> {k})::float8 END)").format(e=expr, p=p, k=sql.Literal(payload_key))
        return expr

    def current_sql(self) -> sql.Composable:
        return self._value_sql(self.current, self.current_factor, "current_mA")

    def voltage_sql(self) -> sql.Composable:
        return self._value_sql(self.voltage, self.voltage_factor, "voltage_mV")

    def device_sql(self, device_id: str | None) -> sql.Composable:
        if device_id:                       # given by hand (--device-id)
            return sql.SQL("{}::text").format(sql.Literal(device_id))
        if self.device:                     # a device column
            return sql.SQL("{}::text").format(sql.Identifier(self.device))
        parts = []
        if self.topic:                      # traffic-nodes/<id>/measurements or traffic-device/<t>/<type>/<id>/status
            t = sql.Identifier(self.topic)
            parts.append(sql.SQL(
                "NULLIF(CASE WHEN split_part({t}, '/', 1) = 'traffic-device' THEN split_part({t}, '/', 4) "
                "ELSE split_part({t}, '/', 2) END, '')").format(t=t))
        if self.serial:
            parts.append(sql.SQL("{}::text").format(sql.Identifier(self.serial)))
        parts.append(sql.SQL("'unknown'::text"))
        return sql.SQL("COALESCE({})").format(sql.SQL(", ").join(parts))

    def usable_rows_sql(self) -> sql.Composable:
        return sql.SQL("SELECT count(*) FROM {}.{} WHERE {} IS NOT NULL AND {} IS NOT NULL AND {} IS NOT NULL").format(
            sql.Identifier(self.schema), sql.Identifier(self.table),
            self.time_sql(), self.current_sql(), self.voltage_sql())

    def fill_report_sql(self) -> tuple[sql.Composable, list[str]]:
        """How many rows have each source filled - explains 0 usable rows."""
        checks = [(c, sql.SQL("count({})").format(sql.Identifier(c)))
                  for c in [self.time, self.time_fallback, self.current, self.voltage] if c]
        if self.payload:
            p = sql.Identifier(self.payload)
            for key in ("current_mA", "voltage_mV"):
                checks.append((f"{self.payload}.{key}", sql.SQL(
                    "count(*) FILTER (WHERE jsonb_typeof({}::jsonb -> {}) = 'number')").format(p, sql.Literal(key))))
        query = sql.SQL("SELECT count(*), {} FROM {}.{}").format(
            sql.SQL(", ").join(expr for _, expr in checks), sql.Identifier(self.schema), sql.Identifier(self.table))
        return query, ["alle Zeilen"] + [name for name, _ in checks]


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
        types = {c.lower(): t for c, t in cols}
        time_col = _pick(by_lower, TIME_NAMES)
        cur = next(((by_lower[n], f) for n, f in CURRENT.items() if n in by_lower), None)
        volt = next(((by_lower[n], f) for n, f in VOLTAGE.items() if n in by_lower), None)
        if not (time_col and cur and volt):
            continue
        m = Mapping(schema, tname, time_col, cur[0], volt[0], cur[1], volt[1], device=_pick(by_lower, DEVICE_NAMES))
        if not m.device:
            m.topic = by_lower.get("topic")
            m.serial = _pick(by_lower, SERIAL_NAMES)
        m.time_fallback = next((by_lower[n] for n in TIME_FALLBACK_NAMES
                                if n in by_lower and by_lower[n] != time_col), None)
        m.payload = next((by_lower[n] for n in PAYLOAD_NAMES if types.get(n) in ("jsonb", "json")), None)
        for target, names in OPTIONAL.items():
            col = _pick(by_lower, names)
            if col:
                m.optional[target] = col
        score = 10 + (5 if m.device else 4 if m.topic else 3 if m.serial else 0) + len(m.optional)
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
    """SELECT returning the columns import_data expects (device_id, measured_at, current_ma, ...)."""
    fields = [
        sql.SQL("{} AS device_id").format(m.device_sql(device_id)),
        sql.SQL("{} AS measured_at").format(m.time_sql()),
        sql.SQL("{} AS current_ma").format(m.current_sql()),
        sql.SQL("{} AS voltage_mv").format(m.voltage_sql()),
    ]
    casts = {"latitude": "float8", "longitude": "float8", "altitude_m": "float8", "satellites": "int",
             "tenant": "text", "device_type": "text"}
    for target, source in m.optional.items():
        fields.append(sql.SQL("{}::{} AS {}").format(sql.Identifier(source), sql.SQL(casts[target]),
                                                     sql.Identifier(target)))
    return sql.SQL("SELECT * FROM (SELECT {} FROM {}.{}) q "
                   "WHERE measured_at IS NOT NULL AND current_ma IS NOT NULL AND voltage_mv IS NOT NULL "
                   "ORDER BY measured_at").format(
        sql.SQL(", ").join(fields), sql.Identifier(m.schema), sql.Identifier(m.table))


def auto_query(dsn: str, table: str | None, device_id: str | None) -> str:
    """Return a ready SQL query for ``import_data sql``, or raise SystemExit with the layout."""
    with psycopg.connect(dsn) as conn:
        conn.execute("SET TIME ZONE 'UTC'")  # timestamps without zone are UTC
        found = candidates(list_tables(conn), table)
        # Several tables may fit by name. Count the usable rows of each (with all
        # fallbacks) and take the best fit that actually contains data.
        for c in found:
            c.rows = conn.execute(c.usable_rows_sql()).fetchone()[0]
            log.info("candidate table %s.%s: %d usable rows", c.schema, c.table, c.rows)
        m = next((c for c in found if c.rows), None)
        if m is None:
            if not found:
                reason = "Keine Tabelle mit Zeit-, Strom- und Spannungsspalten gefunden."
            else:
                reason = "In den passenden Tabellen hat keine Zeile Zeit + Strom + Spannung gleichzeitig.\n"
                for c in found:
                    query, names = c.fill_report_sql()
                    counts = conn.execute(query).fetchone()
                    reason += f"\n{c.schema}.{c.table} - gefüllte Werte:\n" + "\n".join(
                        f"    {n}: {v}" for n, v in zip(names, counts))
            raise SystemExit(
                f"\n{reason}\n\nSo sieht die Datenbank aus (Tabellen, Zeilenzahl, Spalten):\n\n" + describe(conn) +
                "\n\n-> Bitte diese Ausgabe an Claude/das Team schicken, dann wird die Zuordnung angepasst."
            )
        if not (m.device or m.topic or m.serial or device_id):
            log.warning("no device column found, storing everything as device 'unknown' (use --device-id)")
        _resolve_units(conn, m)
        log.info("using %s", m.describe())
        return build_query(m, device_id).as_string(conn)
