"""The "MQTT contract": what a valid node message looks like (docs/MQTT-Vertrag.md).

WHAT THIS FILE DOES
    Every MQTT message has two parts:
      - the TOPIC (the "address" it was sent to), e.g.
            traffic-nodes/101/measurements          <- live broker mqtt.ti-labs.ai
            traffic-device/<tenant>/<type>/<id>/status   <- older recordings, still accepted
        The device id (here "101") is taken FROM THE TOPIC.
      - the PAYLOAD (the content), a JSON text like
            {"current_mA": 551.0, "voltage_mV": 11276.0, "temperature_C": 17.0,
             "lat": 48.2, "lon": 8.6, "altitude_m": 609.6, "satellites": 7,
             "time": "2026-03-19T08:50:50Z"}
        All values in MILLIvolts / MILLIamperes, as the nodes send them.

    ``parse_message(topic, payload)`` checks both and either returns a clean
    ``Measurement`` or raises ``ContractError`` with a German reason, e.g.
    "voltage_mV = 5368709120 ist größer als erlaubt (max. 60000)".

WHO USES IT
    - collector/main.py: checks every received message before saving it.
    - tools/test_publisher.py: ``build_topic``/``build_payload`` create fake
      messages in exactly this format.
    Tests: tests/test_contract.py
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# Default subscriptions of the collector (MQTT_TOPIC overrides them).
# "+" is an MQTT wildcard for exactly one level, so "traffic-nodes/+/measurements"
# matches traffic-nodes/101/measurements, traffic-nodes/102/measurements, ...
DEFAULT_TOPICS = "traffic-nodes/+/measurements,traffic-device/+/+/+/status"
DEFAULT_DEVICE_TYPE = "trafficnode"
# Hard limits for a message to be accepted at all (in mV / mA, like the nodes send).
# Used by the payload check below AND by the import tool, so both apply the same rule.
VOLTAGE_MV_MAX = 60_000      # 60 V; above that it's a read error (node 101: 5368709120 mV)
CURRENT_MA_LIMIT = 100_000   # +-100 A

# Allowed characters in ids taken from the topic: letters, digits, _ . -  (max. 64)
_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class ContractError(ValueError):
    """Raised when a message does not follow the MQTT contract."""


@dataclass(frozen=True)
class TopicInfo:
    """What we learn from the topic alone (before even looking at the content)."""

    device_id: str
    tenant: str | None = None
    device_type: str = DEFAULT_DEVICE_TYPE


def build_topic(device_id: str) -> str:
    """Topic a node with this id publishes to (same layout as the live broker)."""
    return f"traffic-nodes/{device_id}/measurements"


def parse_topic(topic: str) -> TopicInfo:
    """Read the device id (and for old topics tenant/type) from the topic text."""
    parts = topic.split("/")  # "traffic-nodes/101/measurements" -> ["traffic-nodes", "101", "measurements"]
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
    """JSON body published by a TrafficNode. Unknown extra fields are ignored.

    Each line below is one field: its type and the allowed range (ge = >=, gt = >,
    le = <=). The library "pydantic" checks all of them in one go and reports
    every problem it finds. ``float | None`` means "a number or null".
    """

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    # Current in MILLIamperes (the traffic light draws about 500-700 mA).
    current_mA: float = Field(ge=-CURRENT_MA_LIMIT, le=CURRENT_MA_LIMIT)
    # Voltage in MILLIvolts, measured behind the shunt (a 12 V battery = about 12000 mV).
    # 0 mV is what an unconfigured node sends (see docs/samples/sample_msg.json).
    # The node is powered by the battery it measures, so 0 V cannot be real.
    # Above 60 V is a read error (seen live: 5368709120 mV = 1.25 * 2^32 from node 101).
    voltage_mV: float = Field(gt=0, le=VOLTAGE_MV_MAX)
    # GPS position (null when the node has no satellite fix)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    altitude_m: float | None = Field(default=None, ge=-500, le=10_000)
    satellites: int | None = Field(default=None, ge=0, le=100)
    temperature_C: float | None = Field(default=None, ge=-60, le=150)  # degrees Celsius
    # ISO 8601 string or Unix epoch (seconds or milliseconds); null = use receive time.
    time: datetime | None = None

    # Extra check that looks at two fields together (runs after the single-field checks).
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
    """A validated measurement, ready to be stored (one row in the measurements table).

    Note the lower-case field names: these are OUR names (database columns),
    the payload above uses the node's names (current_mA, voltage_mV, ...).
    """

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


# Translation of pydantic's error codes into short German texts for the web page.
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


def within_limits(voltage_mv: float, current_ma: float) -> bool:
    """Same voltage/current rule as the payload check, for data that doesn't
    arrive via MQTT (imports). Also rejects NaN (NaN fails every comparison)."""
    return 0 < voltage_mv <= VOLTAGE_MV_MAX and -CURRENT_MA_LIMIT <= current_ma <= CURRENT_MA_LIMIT


def parse_message(topic: str, payload: bytes | str, received_at: datetime | None = None) -> Measurement:
    """Validate topic and payload; raise ContractError if anything is wrong."""
    # 1. topic -> device id
    info = parse_topic(topic)
    # 2. text -> JSON object
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ContractError(f"kein gültiges JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError("Nachricht muss ein JSON-Objekt sein")
    # 3. check every field against the rules in TelemetryPayload
    try:
        body = TelemetryPayload.model_validate(data)
    except ValidationError as exc:
        raise ContractError("; ".join(_describe(e) for e in exc.errors())) from exc

    # 4. timestamp: the node's "time" if it sent one, otherwise "now" (node 101 sends null).
    #    Everything is stored in UTC; the web page converts to German time.
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
