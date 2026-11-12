"""Private calendar of the service technicians (F13, issue #12).

A technician enters when they want to replace which battery, e.g.
"device 101, Tuesday 08:30, take a spare battery". The calendar page shows these
appointments next to the expected failures of the devices (F12, issue #11; those
come from GET /api/devices, fields estimated_critical_at / estimated_empty_at).

Who may do what:
  techniker            own appointments only: list, create, change, delete.
                       New appointments only for devices assigned to them.
  chef, mitarbeiter,   no access (403): the appointments are private.
  admin
Someone else's appointment id answers 404, so ids of other people's
appointments are not even revealed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from . import queries
from .deps import CurrentUser, get_conn, require_roles
from .models import Appointment, AppointmentCreate, AppointmentWrite

router = APIRouter(prefix="/api/appointments", tags=["Kalender"])

technician_only = require_roles("techniker")


def _utc(value: datetime | None) -> datetime | None:
    """A time without time zone counts as UTC (the web page always sends one)."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _one(conn, appointment_id: int, user: CurrentUser) -> dict:
    rows = conn.execute(queries.APPOINTMENTS.format(where="AND a.id = %(id)s"),
                        {"tech_id": user.id, "id": appointment_id}).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Termin nicht gefunden.")
    return rows[0]


@router.get("", response_model=list[Appointment])
def list_appointments(
    start: datetime | None = Query(None, alias="from", description="only appointments from this time"),
    end: datetime | None = Query(None, alias="to", description="only appointments before this time"),
    conn=Depends(get_conn), user: CurrentUser = Depends(technician_only),
):
    conditions, params = [], {"tech_id": user.id}
    if start is not None:
        conditions.append("AND a.starts_at >= %(start)s")
        params["start"] = _utc(start)
    if end is not None:
        conditions.append("AND a.starts_at < %(end)s")
        params["end"] = _utc(end)
    return conn.execute(queries.APPOINTMENTS.format(where=" ".join(conditions)), params).fetchall()


@router.post("", response_model=Appointment, status_code=201)
def create_appointment(body: AppointmentCreate, conn=Depends(get_conn),
                       user: CurrentUser = Depends(technician_only)):
    row = conn.execute("SELECT technician_id FROM devices WHERE device_id = %s", (body.device_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Gerät nicht gefunden")
    if row["technician_id"] != user.id:
        raise HTTPException(status_code=403, detail="Dieses Gerät ist Ihnen nicht zugeordnet.")
    new = conn.execute(
        "INSERT INTO appointments (technician_id, device_id, starts_at, note) VALUES (%s, %s, %s, %s) RETURNING id",
        (user.id, body.device_id, _utc(body.starts_at), body.note)).fetchone()
    return _one(conn, new["id"], user)


@router.patch("/{appointment_id}", response_model=Appointment)
def update_appointment(appointment_id: int, body: AppointmentWrite, conn=Depends(get_conn),
                       user: CurrentUser = Depends(technician_only)):
    """Move an appointment or change its note. Only the fields sent are changed."""
    _one(conn, appointment_id, user)  # 404 if it isn't theirs
    fields = body.model_fields_set
    if "starts_at" in fields and body.starts_at is None:
        raise HTTPException(status_code=400, detail="Ein Termin braucht Datum und Uhrzeit.")
    if fields:
        sets = ", ".join(f"{f} = %({f})s" for f in fields)
        conn.execute(f"UPDATE appointments SET {sets} WHERE id = %(id)s AND technician_id = %(tech_id)s",
                     {"starts_at": _utc(body.starts_at), "note": body.note, "id": appointment_id, "tech_id": user.id})
    return _one(conn, appointment_id, user)


@router.delete("/{appointment_id}", status_code=204)
def delete_appointment(appointment_id: int, conn=Depends(get_conn), user: CurrentUser = Depends(technician_only)):
    _one(conn, appointment_id, user)
    conn.execute("DELETE FROM appointments WHERE id = %s AND technician_id = %s", (appointment_id, user.id))
