import json
from datetime import datetime, timezone

import pytest

from batterywatch.contract import ContractError, build_payload, build_topic, parse_message, parse_topic

TOPIC = "traffic-device/dieringer-stark/trafficnode/TSN-002/status"
RECEIVED = datetime(2026, 3, 19, 9, 0, tzinfo=timezone.utc)


def payload(**overrides):
    data = {
        "current_mA": 551.0,
        "voltage_mV": 11276.0,
        "lat": 48.201157,
        "lon": 8.649726,
        "altitude_m": 609.6,
        "satellites": 7,
        "time": "2026-03-19T08:50:50Z",
    }
    data.update(overrides)
    return json.dumps(data)


def test_valid_message():
    m = parse_message(TOPIC, payload(), RECEIVED)
    assert (m.tenant, m.device_type, m.device_id) == ("dieringer-stark", "trafficnode", "TSN-002")
    assert m.current_ma == 551.0 and m.voltage_mv == 11276.0
    assert m.latitude == 48.201157 and m.satellites == 7
    assert m.measured_at == datetime(2026, 3, 19, 8, 50, 50, tzinfo=timezone.utc)


def test_missing_time_uses_receive_time():
    m = parse_message(TOPIC, payload(time=None), RECEIVED)
    assert m.measured_at == RECEIVED


@pytest.mark.parametrize("value", [1773910250, 1773910250000])
def test_epoch_time_seconds_and_millis(value):
    m = parse_message(TOPIC, payload(time=value), RECEIVED)
    assert m.measured_at == datetime(2026, 3, 19, 8, 50, 50, tzinfo=timezone.utc)


def test_naive_time_is_utc():
    m = parse_message(TOPIC, payload(time="2026-03-19T08:50:50"), RECEIVED)
    assert m.measured_at.tzinfo is not None
    assert m.measured_at.utcoffset().total_seconds() == 0


def test_gps_may_be_missing():
    m = parse_message(TOPIC, payload(lat=None, lon=None, altitude_m=None, satellites=None), RECEIVED)
    assert m.latitude is None and m.longitude is None


def test_zero_position_means_no_fix():
    m = parse_message(TOPIC, payload(lat=0, lon=0), RECEIVED)
    assert m.latitude is None


def test_unknown_fields_are_ignored():
    m = parse_message(TOPIC, payload(power_W=6.2, firmware="1.2"), RECEIVED)
    assert m.voltage_mv == 11276.0


def test_sample_message_from_docs_is_rejected():
    # docs/samples/sample_msg.json: an unconfigured node sending zeros
    raw = '{"current_mA": 0.00, "voltage_mV": 0.00, "lat": null, "lon": null, "altitude_m": null, "satellites": null, "time": null}'
    with pytest.raises(ContractError, match="voltage_mV"):
        parse_message(TOPIC, raw, RECEIVED)


@pytest.mark.parametrize(
    "raw, match",
    [
        ("{not json", "not valid JSON"),
        ("[1, 2]", "JSON object"),
        (json.dumps({"current_mA": 500}), "voltage_mV"),
        (payload(current_mA="viel"), "current_mA"),
        (payload(voltage_mV=float("nan")), "voltage_mV"),
        (payload(voltage_mV=-5), "voltage_mV"),
        (payload(lat=48.2, lon=None), "lat and lon"),
        (payload(lat=123.0), "lat"),
        (payload(time="gestern"), "time"),
    ],
)
def test_invalid_payloads_are_rejected(raw, match):
    with pytest.raises(ContractError, match=match):
        parse_message(TOPIC, raw, RECEIVED)


@pytest.mark.parametrize(
    "topic",
    [
        "traffic-device/dieringer-stark/trafficnode/TSN-002",
        "other/dieringer-stark/trafficnode/TSN-002/status",
        "traffic-device/dieringer-stark/trafficnode/TSN 002/status",
        "traffic-device/a/b/c/d/status",
    ],
)
def test_invalid_topics_are_rejected(topic):
    with pytest.raises(ContractError):
        parse_topic(topic)


def test_build_payload_round_trip():
    at = datetime(2026, 3, 19, 8, 50, 50, tzinfo=timezone.utc)
    topic = build_topic("demo", "trafficnode", "SIM-001")
    raw = build_payload(630.123, 11850.456, at, 48.1, 8.6, 600.0, 9)
    assert '"time": "2026-03-19T08:50:50Z"' in raw
    m = parse_message(topic, raw, RECEIVED)
    assert m.device_id == "SIM-001" and m.measured_at == at and m.current_ma == 630.12
