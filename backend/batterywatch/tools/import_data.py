"""Import existing (mock / historical) data directly into the BatteryWatch database.

This bypasses MQTT and is meant to pre-fill the database, e.g. with the recorded
sample data, so the frontend has a long history to show right away.

Examples::

    # recorded sample file (InfluxDB CSV export)
    python -m batterywatch.tools.import_data csv ../docs/samples/traffic_devices_signals.csv

    # same, but moved in time so the data ends today (frontend looks "live")
    python -m batterywatch.tools.import_data csv ../docs/samples/traffic_devices_signals.csv --shift-to-now

    # from another PostgreSQL database (e.g. the course's history DB via SSH tunnel);
    # the query must return the columns listed in SQL_COLUMNS (use aliases)
    python -m batterywatch.tools.import_data sql \\
        --source-dsn postgresql://user:pass@localhost:15432/history \\
        --query "SELECT device_id, time AS measured_at, current_ma, voltage_mv, lat AS latitude, \\
                 lon AS longitude, tenant, device_type FROM measurements"
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from ..config import get_settings
from ..contract import Measurement
from ..db import MeasurementStore, ensure_schema
from .samples import read_sample_csv, shift_to

log = logging.getLogger("batterywatch.import")

SQL_COLUMNS = {
    "required": ["device_id", "measured_at", "current_ma", "voltage_mv"],
    "optional": ["tenant", "device_type", "latitude", "longitude", "altitude_m", "satellites"],
}


def _rows_from_sql(dsn: str, query: str) -> list[Measurement]:
    with psycopg.connect(dsn, row_factory=dict_row) as src:
        cur = src.execute(query)
        columns = {c.name for c in cur.description}
        missing = [c for c in SQL_COLUMNS["required"] if c not in columns]
        if missing:
            raise SystemExit(f"query result is missing column(s): {', '.join(missing)}")
        out = []
        for r in cur:
            ts = r["measured_at"]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            out.append(
                Measurement(
                    device_id=str(r["device_id"]),
                    tenant=r.get("tenant") or "unknown",
                    device_type=r.get("device_type") or "trafficnode",
                    measured_at=ts,
                    current_ma=float(r["current_ma"]),
                    voltage_mv=float(r["voltage_mv"]),
                    latitude=r.get("latitude"),
                    longitude=r.get("longitude"),
                    altitude_m=r.get("altitude_m"),
                    satellites=r.get("satellites"),
                )
            )
        return out


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="source", required=True)

    p_csv = sub.add_parser("csv", help="import an InfluxDB CSV export (docs/samples/...)")
    p_csv.add_argument("file")
    p_csv.add_argument("--device-id", help="store the rows under this device id instead of the one in the file")

    p_sql = sub.add_parser("sql", help="import from another PostgreSQL database")
    p_sql.add_argument("--source-dsn", required=True)
    p_sql.add_argument("--query", required=True)

    for p in (p_csv, p_sql):
        p.add_argument("--shift-to-now", action="store_true", help="move timestamps so the data ends today")
        p.add_argument("--database-url", help="target database (default: $DATABASE_URL)")

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.source == "csv":
        rows = read_sample_csv(args.file, device_id=args.device_id)
    else:
        rows = _rows_from_sql(args.source_dsn, args.query)
    # Same plausibility rule as the MQTT contract: 0 V means "no measurement".
    valid = [m for m in rows if m.voltage_mv > 0]
    if len(valid) != len(rows):
        log.warning("skipped %d rows with voltage <= 0", len(rows) - len(valid))
    rows = valid
    if not rows:
        log.warning("nothing to import")
        return 0
    if args.shift_to_now:
        rows = list(shift_to(rows, datetime.now(timezone.utc)))

    store = MeasurementStore(args.database_url or settings.database_url, settings.shunt_resistance_ohm)
    ensure_schema(store.conn)
    inserted = store.save_many(rows, source="import")
    store.close()
    devices = sorted({m.device_id for m in rows})
    log.info(
        "imported %d of %d rows (%d duplicates skipped) for %s, %s .. %s",
        inserted,
        len(rows),
        len(rows) - inserted,
        ", ".join(devices),
        rows[0].measured_at.isoformat(timespec="minutes"),
        rows[-1].measured_at.isoformat(timespec="minutes"),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
