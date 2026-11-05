"""MQTT contract: topic layout and payload validation (see docs/MQTT-Vertrag.md).

Topic (live broker mqtt.ti-labs.ai):   traffic-nodes/<device_id>/measurements
Topic (older recordings, still read):  traffic-device/<tenant>/<device_type>/<device_id>/status
Payload: {"current_mA": 551.0, "voltage_mV": 11276.0, "temperature_C": 17.0, "lat": 48.2,
          "lon": 8.6, "altitude_m": 609.6, "satellites": 7, "time": "2026-03-19T08:50:50Z"}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# Default subscriptions of the collector (MQTT_TOPIC overrides them)
DEFAULT_TOPICS = "traffic-nodes/+/measurements,traffic-device/+/+/+/status"
DEFAULT_DEVICE_TYPE = "trafficnode"
_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class ContractError(ValueError):
    """Raised when a message does not follow the MQTT contract."""


@dataclass(frozen=True)
class TopicInfo:
    device_id: str
    tenant: str | None = None
    device_type: str = DEFAULT_DEVICE_TYPE


def build_topic(device_id: str) -> str:
    return f"traffic-nodes/{device_id}/measurements"


def parse_topic(topic: str) -> TopicInfo:
    parts = topic.split("/")
    if len(parts) == 3 and parts[0] == "traffic-nodes" and parts[2] == "measurements":
        info = TopicInfo(device_id=parts[1])
    elif len(parts) == 5 and parts[0] == "traffic-device" and parts[4] == "status":
        info = TopicInfo(device_id=parts[3], tenant=parts[1], device_type=parts[2])
    else:
        raise ContractError(f"unbekanntes Topic-Format: {topic!r}")
    for name in ("tenant", "device_type", "device_id"):
        value = getattr(info, name)
        if value is not None and not _ID_RE.match(value):
            raise ContractError(f"ungültige {name} im Topic: {value!r}")
    return info


class TelemetryPayload(BaseModel):
    """JSON body published by a TrafficNode. Unknown extra fields are ignored."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    current_mA: float = Field(ge=-100_000, le=100_000)
    # 0 mV is what an unconfigured node sends (see docs/samples/sample_msg.json).
    # The node is powered by the battery it measures, so 0 V cannot be real.
    # Above 60 V is a read error (seen live: 5368709120 mV = 1.25 * 2^32 from node 101).
    voltage_mV: float = Field(gt=0, le=60_000)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    altitude_m: float | None = Field(default=None, ge=-500, le=10_000)
    satellites: int | None = Field(default=None, ge=0, le=100)
    temperature_C: float | None = Field(default=None, ge=-60, le=150)
    # ISO 8601 string or Unix epoch (seconds or milliseconds); null = use receive time.
    time: datetime | None = None

    @model_validator(mode="after")
    def _position_complete(self) -> "TelemetryPayload":
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat und lon müssen beide gesetzt oder beide null sein")
        if self.lat == 0 and self.lon == 0:
            # 0/0 is the typical "no GPS fix" value, treat it as unknown.
            self.lat = self.lon = None
        return self


@dataclass(frozen=True)
class Measurement:
    """A validated measurement, ready to be stored."""

    device_id: str
    tenant: str | None
    device_type: str
    measured_at: datetime
    current_ma: float
    voltage_mv: float
    latitude: float | None
    longitude: float | None
    altitude_m: float | None
    satellites: int | None
    temperature_c: float | None = None


_ERROR_TEXT = {
    "missing": "fehlt",
    "float_parsing": "ist keine Zahl",
    "float_type": "ist keine Zahl",
    "int_parsing": "ist keine Ganzzahl",
    "int_from_float": "ist keine Ganzzahl",
    "finite_number": "ist keine endliche Zahl",
    "less_than_equal": "ist größer als erlaubt (max. {le})",
    "greater_than": "muss größer als {gt} sein",
    "greater_than_equal": "ist kleiner als erlaubt (min. {ge})",
    "datetime_from_date_parsing": "ist keine gültige Zeitangabe",
    "datetime_parsing": "ist keine gültige Zeitangabe",
    "datetime_type": "ist keine gültige Zeitangabe",
}


def _describe(err: dict) -> str:
    """One validation error as short German text, including the offending value."""
    def show(v):
        return int(v) if isinstance(v, float) and v.is_integer() else v

    field = ".".join(map(str, err["loc"])) or "Nachricht"
    template = _ERROR_TEXT.get(err["type"])
    text = template.format(**{k: show(v) for k, v in err.get("ctx", {}).items()}) if template else err["msg"]
    if err["type"] == "missing" or "input" not in err or isinstance(err["input"], dict):
        return f"{field} {text}"
    return f"{field} = {show(err['input'])!r} {text}"


def parse_message(topic: str, payload: bytes | str, received_at: datetime | None = None) -> Measurement:
    """Validate topic and payload; raise ContractError if anything is wrong."""
    info = parse_topic(topic)
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ContractError(f"kein gültiges JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError("Nachricht muss ein JSON-Objekt sein")
    try:
        body = TelemetryPayload.model_validate(data)
    except ValidationError as exc:
        raise ContractError("; ".join(_describe(e) for e in exc.errors())) from exc

    received_at = received_at or datetime.now(timezone.utc)
    measured_at = body.time or received_at
    if measured_at.tzinfo is None:
        measured_at = measured_at.replace(tzinfo=timezone.utc)

    return Measurement(
        device_id=info.device_id,
        tenant=info.tenant,
        device_type=info.device_type,
        measured_at=measured_at,
        current_ma=body.current_mA,
        voltage_mv=body.voltage_mV,
        latitude=body.lat,
        longitude=body.lon,
        altitude_m=body.altitude_m,
        satellites=body.satellites,
        temperature_c=body.temperature_C,
    )


def build_payload(
    current_ma: float,
    voltage_mv: float,
    measured_at: datetime | None,
    lat: float | None = None,
    lon: float | None = None,
    altitude_m: float | None = None,
    satellites: int | None = None,
    temperature_c: float | None = None,
) -> str:
    """Serialize a payload exactly like the contract describes (used by the test publisher)."""
    return json.dumps(
        {
            "current_mA": round(current_ma, 2),
            "voltage_mV": round(voltage_mv, 2),
            "temperature_C": round(temperature_c, 2) if temperature_c is not None else None,
            "lat": lat,
            "lon": lon,
            "altitude_m": altitude_m,
            "satellites": satellites,
            "time": measured_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if measured_at else None,
        }
    )
