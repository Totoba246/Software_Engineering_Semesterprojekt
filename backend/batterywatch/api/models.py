"""Shapes of the JSON the API receives and sends.

FastAPI uses these classes to check incoming data (wrong types / too long ->
automatic error 422) and to build the documentation at /docs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .. import battery

Role = Literal["admin", "chef", "mitarbeiter", "techniker"]
DEVICE_ID_PATTERN = r"^[A-Za-z0-9_.-]{1,64}$"  # same rule as the MQTT topic (contract.py)


def _blank_to_none(value):
    """'' or '   ' from a form field means 'no value'."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


# --- Status rules ----------------------------------------------------------------
class StatusRules(BaseModel):
    critical_below_percent: float
    low_below_percent: float
    soc_curve: list[tuple[float, float]]
    smoothing_minutes: int
    stale_after_minutes: int
    shunt_resistance_ohm: float


# --- Devices -----------------------------------------------------------------------
class Position(BaseModel):
    latitude: float
    longitude: float
    altitude_m: float | None = None
    satellites: int | None = None
    source: Literal["gps", "manuell"] = "gps"  # from the node, or entered by hand


class Technician(BaseModel):
    id: int
    display_name: str


class DeviceSummary(BaseModel):
    """One device in the overview list (answer of GET /api/devices)."""

    device_id: str
    name: str
    tenant: str | None
    device_type: str
    category: str | None
    location: str | None
    technician: Technician | None  # only shown to Firmenchef/Mitarbeiter
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


class DeviceDetail(DeviceSummary):
    """Everything from DeviceSummary plus extra figures for the detail page."""

    measurement_count: int
    first_seen: datetime | None
    avg_current_a_24h: float | None
    voltage_trend_v_per_day: float | None
    # Simple prediction (F04): straight line through the 72 h trend
    estimated_critical_at: datetime | None
    estimated_empty_at: datetime | None


class DeviceWrite(BaseModel):
    """Master data a Firmenchef/Mitarbeiter can set (F07). Empty fields = no value."""

    name: str | None = Field(None, max_length=100)
    category: str | None = Field(None, max_length=60)
    location: str | None = Field(None, max_length=120)
    latitude: float | None = Field(None, ge=-90, le=90)    # manual position for nodes without GPS
    longitude: float | None = Field(None, ge=-180, le=180)
    technician_id: int | None = None

    _blank = field_validator("name", "category", "location", mode="before")(_blank_to_none)


class DeviceCreate(DeviceWrite):
    # Must be exactly the id in the node's MQTT topic, e.g. 101 for traffic-nodes/101/measurements
    device_id: str = Field(pattern=DEVICE_ID_PATTERN)

    @field_validator("device_id", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


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


class Message(BaseModel):
    """One received MQTT message (answer of GET /api/devices/{id}/messages)."""

    received_at: datetime
    topic: str
    accepted: bool
    error: str | None
    payload: str


# --- Login -----------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class Me(BaseModel):
    id: int
    username: str
    display_name: str
    email: str | None
    role: Role
    must_change_password: bool


# --- User management (admin) -----------------------------------------------------
class User(BaseModel):
    id: int
    username: str
    display_name: str
    email: str | None
    role: Role
    active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None
    device_count: int  # devices assigned (technicians)


class UserCreate(BaseModel):
    username: str = Field(max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(None, max_length=200)
    role: Role
    password: str | None = Field(None, max_length=200)  # empty = generate a start password

    _blank = field_validator("email", "password", mode="before")(_blank_to_none)


class UserUpdate(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=100)
    email: str | None = Field(None, max_length=200)
    role: Role | None = None
    active: bool | None = None          # false = lock
    reset_password: bool = False         # true = new start password, must be changed at next login

    _blank = field_validator("email", mode="before")(_blank_to_none)


class UserWithPassword(User):
    """Answer when an account was created or its password reset: the start
    password is shown ONCE to the admin, who passes it on."""

    start_password: str | None = None
