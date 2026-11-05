"""Reader for the recorded sample data (docs/samples/traffic_devices_signals.csv).

This CSV file contains 2229 real messages of one node (TSN-002, March 2026,
every 3 minutes). NOTE: unlike the live nodes, this file is in VOLTS and
AMPERES (voltage_V, current_A) - the reader converts to mV/mA (x 1000).

The file is an InfluxDB export with one row per TrafficNode message, e.g.::

    _time,_measurement,device_id,device_type,serial,tenant,topic,altitude_m,current_A,
    latitude,longitude,power_W,speed_mps,voltage_V

Used by the import tool (CSV -> database) and the test publisher (CSV -> MQTT replay).
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator

from ..contract import Measurement

_FRACTION_RE = re.compile(r"(\.\d{6})\d+")


def parse_time(value: str) -> datetime:
    """Parse RFC 3339 timestamps, including Influx' nanosecond precision."""
    value = _FRACTION_RE.sub(r"\1", value.strip()).replace("Z", "+00:00")
    ts = datetime.fromisoformat(value)
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _float(row: dict, *names: str) -> float | None:
    for name in names:
        raw = row.get(name)
        if raw not in (None, "", "null", "NaN"):
            return float(raw)
    return None


def read_sample_csv(path: str | Path, device_id: str | None = None) -> list[Measurement]:
    """Read all rows, sorted by time. ``device_id`` optionally renames the device."""
    out: list[Measurement] = []
    with open(path, newline="", encoding="utf-8") as fh:
        lines = (line for line in fh if line.strip() and not line.startswith("#"))
        for row in csv.DictReader(lines):
            if row.get("_time") in (None, "", "_time"):  # repeated header of a second table
                continue
            current_ma = _float(row, "current_mA")
            if current_ma is None:
                current_ma = _float(row, "current_A") * 1000
            voltage_mv = _float(row, "voltage_mV")
            if voltage_mv is None:
                voltage_mv = _float(row, "voltage_V") * 1000
            sats = _float(row, "satellites")
            out.append(
                Measurement(
                    device_id=device_id or row["device_id"],
                    tenant=row.get("tenant") or None,
                    device_type=row.get("device_type") or "trafficnode",
                    measured_at=parse_time(row["_time"]),
                    current_ma=current_ma,
                    voltage_mv=voltage_mv,
                    latitude=_float(row, "latitude", "lat"),
                    longitude=_float(row, "longitude", "lon"),
                    altitude_m=_float(row, "altitude_m"),
                    satellites=int(sats) if sats is not None else None,
                )
            )
    out.sort(key=lambda m: m.measured_at)
    return out


def shift_to(
    measurements: Iterable[Measurement], new_end: datetime, keep_time_of_day: bool = True
) -> Iterator[Measurement]:
    """Move all timestamps so that the newest measurement lies at (or just before) ``new_end``.

    Handy to make months-old recordings look "live" in the frontend.
    With ``keep_time_of_day`` the shift is a whole number of days, so the night
    dimming of the traffic light still happens at night; the newest measurement
    then lies up to 24 h before ``new_end``.
    """
    items = list(measurements)
    if not items:
        return
    offset = new_end - max(m.measured_at for m in items)
    if keep_time_of_day:
        offset = timedelta(days=offset // timedelta(days=1))
    for m in items:
        yield Measurement(**{**m.__dict__, "measured_at": m.measured_at + offset})
