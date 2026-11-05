"""MQTT contract: topic layout and payload validation (see docs/MQTT-Vertrag.md).

Topic:   traffic-device/<tenant>/<device_type>/<device_id>/status
Payload: {"current_mA": 551.0, "voltage_mV": 11276.0, "lat": 48.2, "lon": 8.6,
          "altitude_m": 609.6, "satellites": 7, "time": "2026-03-19T08:50:50Z"}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

TOPIC_PREFIX = "traffic-device"
TOPIC_SUFFIX = "status"
_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class ContractError(ValueError):
    """Raised when a message does not follow the MQTT contract."""


@dataclass(frozen=True)
class TopicInfo:
    tenant: str
    device_type: str
    device_id: str


def build_topic(tenant: str, device_type: str, device_id: str) -> str:
    return f"{TOPIC_PREFIX}/{tenant}/{device_type}/{device_id}/{TOPIC_SUFFIX}"


def parse_topic(topic: str) -> TopicInfo:
    parts = topic.split("/")
    if len(parts) != 5 or parts[0] != TOPIC_PREFIX or parts[4] != TOPIC_SUFFIX:
        raise ContractError(f"unexpected topic layout: {topic!r}")
    tenant, device_type, device_id = parts[1:4]
    for name, value in (("tenant", tenant), ("device_type", device_type), ("device_id", device_id)):
        if not _ID_RE.match(value):
            raise ContractError(f"invalid {name} in topic: {value!r}")
    return TopicInfo(tenant=tenant, device_type=device_type, device_id=device_id)


class TelemetryPayload(BaseModel):
    """JSON body published by a TrafficNode. Unknown extra fields are ignored."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    current_mA: float = Field(ge=-100_000, le=100_000)
    # 0 mV is what an unconfigured node sends (see docs/samples/sample_msg.json).
    # The node is powered by the battery it measures, so 0 V cannot be real.
    voltage_mV: float = Field(gt=0, le=60_000)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    altitude_m: float | None = Field(default=None, ge=-500, le=10_000)
    satellites: int | None = Field(default=None, ge=0, le=100)
    # ISO 8601 string or Unix epoch (seconds or milliseconds); null = use receive time.
    time: datetime | None = None

    @model_validator(mode="after")
    def _position_complete(self) -> "TelemetryPayload":
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must both be set or both be null")
        if self.lat == 0 and self.lon == 0:
            # 0/0 is the typical "no GPS fix" value, treat it as unknown.
            self.lat = self.lon = None
        return self


@dataclass(frozen=True)
class Measurement:
    """A validated measurement, ready to be stored."""

    device_id: str
    tenant: str
    device_type: str
    measured_at: datetime
    current_ma: float
    voltage_mv: float
    latitude: float | None
    longitude: float | None
    altitude_m: float | None
    satellites: int | None


def parse_message(topic: str, payload: bytes | str, received_at: datetime | None = None) -> Measurement:
    """Validate topic and payload; raise ContractError if anything is wrong."""
    info = parse_topic(topic)
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ContractError(f"payload is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError("payload must be a JSON object")
    try:
        body = TelemetryPayload.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'payload'}: {e['msg']}" for e in exc.errors())
        raise ContractError(f"payload violates contract: {details}") from exc

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
    )


def build_payload(
    current_ma: float,
    voltage_mv: float,
    measured_at: datetime | None,
    lat: float | None = None,
    lon: float | None = None,
    altitude_m: float | None = None,
    satellites: int | None = None,
) -> str:
    """Serialize a payload exactly like the contract describes (used by the test publisher)."""
    return json.dumps(
        {
            "current_mA": round(current_ma, 2),
            "voltage_mV": round(voltage_mv, 2),
            "lat": lat,
            "lon": lon,
            "altitude_m": altitude_m,
            "satellites": satellites,
            "time": measured_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if measured_at else None,
        }
    )
