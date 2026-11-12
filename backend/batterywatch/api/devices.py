"""Device endpoints: overview, detail, history, messages (F01, F03, F10, F11)
and master data / technician assignment (F07, F09). Every device comes with the
simple prediction (F04), which the calendar (F12) shows.

Who may do what (use-case diagram):
  chef, mitarbeiter  see all devices; add, edit, delete devices; assign technicians
  techniker          sees ONLY the devices assigned to them (others: 403)
  admin              no device access (user management only)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from .. import battery, security
from ..config import Settings
from . import queries
from .deps import CurrentUser, get_conn, get_settings, require_roles
from .models import (
    DeviceCreate, DeviceDetail, DeviceSummary, DeviceWrite, History, HistoryPoint, Message,
    Position, StatusRules, Technician,
)

router = APIRouter(prefix="/api", tags=["Geräte"])

# Who may READ device data, and who may CHANGE it
viewer = require_roles("chef", "mitarbeiter", "techniker")
manager = require_roles(*security.MANAGEMENT)

# The chart can't draw thousands of points nicely, so measurements are grouped into
# time slots ("buckets") and averaged. Candidate slot sizes in seconds (3 min ... 1 day);
# the smallest one that yields at most MAX_POINTS points is used.
BUCKETS = [180, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400]
MAX_POINTS = 500


# --- reading -------------------------------------------------------------------------
def _summarize(row: dict, now: datetime, s: Settings, user: CurrentUser) -> dict:
    """One database row (mV, mA, timestamps) -> answer for the web page (V, A, %, status)."""
    avg_mv = row["avg_battery_voltage_mv"]  # average of the last 60 min, in mV
    volts = round(avg_mv / 1000, 3) if avg_mv is not None else None
    soc = battery.state_of_charge(volts, s.soc_curve)
    last_seen, last_msg = row["last_seen"], row["last_message_at"]
    minutes = (now - last_seen).total_seconds() / 60 if last_seen else None
    msg_minutes = (now - last_msg).total_seconds() / 60 if last_msg else None

    position = None
    if row["latitude"] is not None:  # None = the node never sent a GPS position
        position = Position(latitude=round(row["latitude"], 6), longitude=round(row["longitude"], 6),
                            altitude_m=round(row["altitude_m"], 1) if row["altitude_m"] is not None else None,
                            satellites=row["satellites"], fixes=row["fixes"], days=s.position_days)

    technician = None
    if user.is_management and row["technician_id"] is not None:  # README F11: only for Betreiber
        technician = Technician(id=row["technician_id"], display_name=row["technician_name"])

    def mv_to_v(v):
        return round(v / 1000, 3) if v is not None else None

    trend = round(row["trend_v_per_day"], 3) if row["trend_v_per_day"] is not None else None
    critical_at, empty_at = _prediction(volts, last_seen, trend, s)

    return dict(
        device_id=row["device_id"], name=row["name"] or row["device_id"],
        tenant=row["tenant"], device_type=row["device_type"],
        category=row["category"], location=row["location"], technician=technician,
        last_seen=last_seen,
        minutes_since_last_seen=round(minutes, 1) if minutes is not None else None,
        stale=minutes is None or minutes > s.stale_after_minutes,
        battery_voltage_v=volts,
        last_battery_voltage_v=mv_to_v(row["last_battery_voltage_mv"]),
        current_a=mv_to_v(row["last_current_ma"]),  # mA -> A, same factor
        temperature_c=round(row["temperature_c"], 1) if row["temperature_c"] is not None else None,
        soc_percent=round(soc, 1) if soc is not None else None,
        status=battery.classify(soc, s.status_critical_below, s.status_low_below),
        position=position,
        last_message_at=last_msg,
        minutes_since_last_message=round(msg_minutes, 1) if msg_minutes is not None else None,
        last_message_error=row["last_message_error"] if row["last_message_accepted"] is False else None,
        voltage_trend_v_per_day=trend,
        estimated_critical_at=critical_at, estimated_empty_at=empty_at,
    )


def _prediction(volts: float | None, last_seen: datetime | None, trend: float | None,
                s: Settings) -> tuple[datetime | None, datetime | None]:
    """Prediction (F04, simple): when does the falling voltage reach "critical" / "empty"?
    Counted from the newest measurement; more than a year ahead counts as "no estimate"."""
    if volts is None or last_seen is None:
        return None, None
    result = []
    for target_pct in (s.status_critical_below, 0):
        hours = battery.hours_until(volts, battery.voltage_for_soc(target_pct, s.soc_curve), trend)
        result.append(last_seen + timedelta(hours=hours) if hours is not None and hours < 24 * 365 else None)
    return result[0], result[1]


def _fetch_states(conn, s: Settings, user: CurrentUser, device_id: str | None = None) -> list[dict]:
    conditions, params = [], {"window_minutes": s.smoothing_minutes, "position_days": s.position_days}
    if device_id is not None:
        conditions.append("d.device_id = %(device_id)s")
        params["device_id"] = device_id
    if user.role == "techniker":  # technicians: only their own devices
        conditions.append("d.technician_id = %(tech_id)s")
        params["tech_id"] = user.id
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = conn.execute(queries.DEVICE_STATE.format(where=where), params).fetchall()
    now = datetime.now(timezone.utc)
    return [_summarize(r, now, s, user) for r in rows]


def _check_access(conn, device_id: str, user: CurrentUser) -> None:
    """404 if the device doesn't exist, 403 if a technician asks for someone else's."""
    row = conn.execute("SELECT technician_id FROM devices WHERE device_id = %s", (device_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Gerät nicht gefunden")
    if user.role == "techniker" and row["technician_id"] != user.id:
        raise HTTPException(status_code=403, detail="Dieses Gerät ist Ihnen nicht zugeordnet.")


@router.get("/status-rules", response_model=StatusRules)
def status_rules(s: Settings = Depends(get_settings), user=Depends(viewer)):
    return StatusRules(
        critical_below_percent=s.status_critical_below, low_below_percent=s.status_low_below,
        soc_curve=s.soc_curve, smoothing_minutes=s.smoothing_minutes,
        stale_after_minutes=s.stale_after_minutes, shunt_resistance_ohm=s.shunt_resistance_ohm,
    )


@router.get("/devices", response_model=list[DeviceSummary])
def list_devices(conn=Depends(get_conn), s: Settings = Depends(get_settings), user=Depends(viewer)):
    return _fetch_states(conn, s, user)


@router.get("/devices/{device_id}", response_model=DeviceDetail)
def get_device(device_id: str, conn=Depends(get_conn), s: Settings = Depends(get_settings),
               user=Depends(viewer)):
    _check_access(conn, device_id, user)
    state = _fetch_states(conn, s, user, device_id)[0]
    stats = {"measurement_count": 0, "first_seen": None, "avg_current_ma_24h": None}
    if state["last_seen"] is not None:
        stats = conn.execute(queries.DEVICE_STATS, {"device_id": device_id, "last_seen": state["last_seen"]}).fetchone()
    avg_ma = stats["avg_current_ma_24h"]
    return DeviceDetail(
        **state,
        measurement_count=stats["measurement_count"], first_seen=stats["first_seen"],
        avg_current_a_24h=round(avg_ma / 1000, 3) if avg_ma is not None else None,
    )


@router.get("/devices/{device_id}/history", response_model=History)
def get_history(
    device_id: str,
    hours: int = Query(168, ge=1, le=24 * 365, description="Length of the time range in hours"),
    end: datetime | None = Query(None, description="End of the range; default = last measurement"),
    conn=Depends(get_conn), s: Settings = Depends(get_settings), user=Depends(viewer),
):
    _check_access(conn, device_id, user)
    # The range ends at the device's NEWEST measurement (not "now"), so old or
    # imported data still shows a chart instead of an empty one.
    if end is None:
        row = conn.execute(queries.LAST_SEEN, {"device_id": device_id}).fetchone()
        end = row["last_seen"] or datetime.now(timezone.utc)
    elif end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = end - timedelta(hours=hours)
    bucket = next((b for b in BUCKETS if hours * 3600 / b <= MAX_POINTS), BUCKETS[-1])
    rows = conn.execute(queries.HISTORY, {"device_id": device_id, "bucket_seconds": bucket,
                                          "start": start, "end": end}).fetchall()
    points = [
        HistoryPoint(
            t=r["t"],
            battery_voltage_v=round(r["avg_mv"] / 1000, 3),
            battery_voltage_min_v=round(r["min_mv"] / 1000, 3),
            battery_voltage_max_v=round(r["max_mv"] / 1000, 3),
            current_a=round(r["avg_ma"] / 1000, 3),
            soc_percent=round(battery.state_of_charge(r["avg_mv"] / 1000, s.soc_curve), 1),
            samples=r["n"],
        )
        for r in rows
    ]
    return History(device_id=device_id, start=start, end=end, bucket_seconds=bucket, points=points)


@router.get("/devices/{device_id}/messages", response_model=list[Message])
def get_messages(device_id: str, limit: int = Query(20, ge=1, le=500), conn=Depends(get_conn),
                 user=Depends(viewer)):
    """Newest received MQTT messages of a device, including rejected ones."""
    _check_access(conn, device_id, user)
    return conn.execute(queries.MESSAGES, {"device_id": device_id, "limit": limit}).fetchall()


# --- changing (Firmenchef / Mitarbeiter) ------------------------------------------------
@router.get("/technicians", response_model=list[Technician])
def list_technicians(conn=Depends(get_conn), user=Depends(manager)):
    """Active service technicians, for the "assign technician" dropdown."""
    return conn.execute("SELECT id, display_name FROM users WHERE role = 'techniker' AND active "
                        "ORDER BY display_name").fetchall()


def _check_technician(conn, technician_id: int | None) -> None:
    if technician_id is None:
        return
    ok = conn.execute("SELECT 1 FROM users WHERE id = %s AND role = 'techniker' AND active",
                      (technician_id,)).fetchone()
    if not ok:
        raise HTTPException(status_code=400, detail="Diesen Servicetechniker gibt es nicht (oder er ist gesperrt).")


# which DeviceWrite field goes into which database column
_COLUMNS = {"name": "name", "category": "category", "location": "location", "technician_id": "technician_id"}


@router.post("/devices", response_model=DeviceDetail, status_code=201)
def create_device(body: DeviceCreate, conn=Depends(get_conn), s: Settings = Depends(get_settings),
                  user=Depends(manager)):
    """Register a node in advance (before its first message), with master data.
    The device_id must match the id in its MQTT topic, e.g. traffic-nodes/<id>/measurements."""
    _check_technician(conn, body.technician_id)
    try:
        conn.execute(
            "INSERT INTO devices (device_id, device_type, name, category, location, technician_id) "
            "VALUES (%s, 'trafficnode', %s, %s, %s, %s)",
            (body.device_id, body.name, body.category, body.location, body.technician_id))
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail=f"Ein Gerät mit der ID {body.device_id} gibt es schon.")
    return get_device(body.device_id, conn, s, user)


@router.patch("/devices/{device_id}", response_model=DeviceDetail)
def update_device(device_id: str, body: DeviceWrite, conn=Depends(get_conn),
                  s: Settings = Depends(get_settings), user=Depends(manager)):
    """Change master data. Only the fields sent are changed; null clears a field."""
    _check_access(conn, device_id, user)
    fields = body.model_fields_set
    if "technician_id" in fields:
        _check_technician(conn, body.technician_id)
    if fields:
        sets = ", ".join(f"{_COLUMNS[f]} = %({f})s" for f in fields)
        conn.execute(f"UPDATE devices SET {sets} WHERE device_id = %(device_id)s",
                     {**body.model_dump(), "device_id": device_id})
    return get_device(device_id, conn, s, user)


@router.delete("/devices/{device_id}", status_code=204)
def delete_device(device_id: str, conn=Depends(get_conn), user=Depends(manager)):
    """Delete a device with ALL its measurements and messages. If the node keeps
    sending, the collector registers it again with the next message."""
    _check_access(conn, device_id, user)
    conn.execute("DELETE FROM raw_messages WHERE device_id = %s", (device_id,))
    conn.execute("DELETE FROM devices WHERE device_id = %s", (device_id,))  # measurements follow (CASCADE)
