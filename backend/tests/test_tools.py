import random
from datetime import datetime, timedelta, timezone

import pytest

from batterywatch.contract import parse_message
from batterywatch.tools.samples import parse_time, read_sample_csv, shift_to
from batterywatch.tools.test_publisher import make_nodes

from .conftest import SAMPLE_CSV

ANCHOR = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


def test_parse_time_with_nanoseconds():
    assert parse_time("2026-03-19T08:50:50.836520127Z") == datetime(
        2026, 3, 19, 8, 50, 50, 836520, tzinfo=timezone.utc
    )


def test_read_sample_csv_converts_units():
    rows = read_sample_csv(SAMPLE_CSV)
    assert len(rows) == 2229
    first = rows[0]
    assert first.device_id == "TSN-002" and first.tenant == "dieringer-stark"
    assert first.current_ma == pytest.approx(551.0)
    assert first.voltage_mv == pytest.approx(11276.0)
    assert (first.latitude, first.longitude) == (48.201157, 8.649726)
    assert rows == sorted(rows, key=lambda m: m.measured_at)


def test_shift_to_keeps_time_of_day_and_ends_before_target():
    rows = read_sample_csv(SAMPLE_CSV)[:50]
    shifted = list(shift_to(rows, ANCHOR))
    assert ANCHOR - timedelta(days=1) < shifted[-1].measured_at <= ANCHOR
    assert shifted[0].measured_at.time() == rows[0].measured_at.time()
    assert shifted[1].measured_at - shifted[0].measured_at == rows[1].measured_at - rows[0].measured_at


def test_simulated_nodes_have_different_states_now():
    nodes = make_nodes(8, seed=1, anchor=ANCHOR)
    volts = sorted(n.open_circuit_voltage(ANCHOR) for n in nodes)
    assert volts[0] < 11.3 and volts[-1] > 12.3


def test_simulated_battery_drains_and_gets_swapped():
    node = make_nodes(1, seed=1, anchor=ANCHOR)[0]
    later = node.open_circuit_voltage(ANCHOR + timedelta(days=1))
    assert later == pytest.approx(node.open_circuit_voltage(ANCHOR) - node.drain_v_per_day)
    for days in range(0, 120):
        ocv = node.open_circuit_voltage(ANCHOR + timedelta(days=days))
        assert node.empty_v <= ocv < node.full_v


def test_simulated_night_dimming_draws_less_current():
    node = make_nodes(1, seed=1, anchor=ANCHOR)[0]
    rng = random.Random(0)
    day = [node.sample(datetime(2026, 11, 5, 11, m, tzinfo=timezone.utc), rng)["current_ma"] for m in range(60)]
    night = [node.sample(datetime(2026, 11, 5, 1, m, tzinfo=timezone.utc), rng)["current_ma"] for m in range(60)]
    assert sum(night) / 60 < sum(day) / 60 - 60


def test_simulated_message_satisfies_contract():
    from batterywatch.contract import build_payload, build_topic

    node = make_nodes(1, seed=1, anchor=ANCHOR)[0]
    s = node.sample(ANCHOR, random.Random(0))
    raw = build_payload(s["current_ma"], s["voltage_mv"], ANCHOR, s["lat"], s["lon"], s["altitude_m"], s["satellites"],
                        s["temperature_c"])
    m = parse_message(build_topic(node.device_id), raw)
    assert m.device_id == "SIM-001" and m.measured_at == ANCHOR
    assert -10 < m.temperature_c < 30


# --- column detection for the history database ---------------------------------
from batterywatch.tools.history_source import guess_mapping  # noqa: E402


def test_guess_mapping_influx_style_columns():
    tables = {
        ("public", "users"): [("id", "integer"), ("name", "text")],
        ("public", "traffic_device_status"): [
            ("_time", "timestamp with time zone"), ("device_id", "text"), ("tenant", "text"),
            ("current_A", "double precision"), ("voltage_V", "double precision"),
            ("latitude", "double precision"), ("longitude", "double precision"), ("altitude_m", "double precision"),
        ],
    }
    m = guess_mapping(tables)
    assert (m.table, m.time, m.device, m.current, m.voltage) == (
        "traffic_device_status", "_time", "device_id", "current_A", "voltage_V")
    assert (m.current_factor, m.voltage_factor) == (1000.0, 1000.0)
    assert m.optional == {"latitude": "latitude", "longitude": "longitude", "altitude_m": "altitude_m", "tenant": "tenant"}


def test_guess_mapping_without_units_or_device():
    m = guess_mapping({("public", "messwerte"): [("ts", "timestamp"), ("current", "real"), ("voltage", "real")]})
    assert m.device is None and m.current_factor is None and m.voltage_factor is None


def test_guess_mapping_none_when_no_table_fits():
    assert guess_mapping({("public", "users"): [("id", "integer")]}) is None
