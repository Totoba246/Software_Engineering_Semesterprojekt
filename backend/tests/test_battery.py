import pytest

from batterywatch.battery import BatteryStatus, battery_voltage_mv, classify, state_of_charge

CURVE = [(10.5, 0.0), (12.7, 100.0)]


def test_battery_voltage_adds_shunt_drop():
    # U_bat = 0.002 Ohm * I + U_measured; 551 mA * 0.002 Ohm = 1.102 mV
    assert battery_voltage_mv(11276.0, 551.0) == pytest.approx(11277.102)


def test_battery_voltage_without_current_is_measured_voltage():
    assert battery_voltage_mv(12000.0, 0.0) == 12000.0


def test_battery_voltage_uses_configured_shunt():
    assert battery_voltage_mv(12000.0, 1000.0, shunt_resistance_ohm=0.01) == pytest.approx(12010.0)


@pytest.mark.parametrize(
    "volts, expected",
    [(10.5, 0), (12.7, 100), (11.6, 50), (9.0, 0), (14.0, 100), (11.05, 25)],
)
def test_state_of_charge_linear_and_clamped(volts, expected):
    assert state_of_charge(volts, CURVE) == pytest.approx(expected)


def test_state_of_charge_piecewise():
    curve = [(11.0, 0), (12.0, 80), (12.5, 100)]
    assert state_of_charge(11.5, curve) == pytest.approx(40)
    assert state_of_charge(12.25, curve) == pytest.approx(90)


def test_state_of_charge_unknown():
    assert state_of_charge(None, CURVE) is None


@pytest.mark.parametrize(
    "soc, status",
    [
        (None, BatteryStatus.UNKNOWN),
        (0, BatteryStatus.CRITICAL),
        (19.9, BatteryStatus.CRITICAL),
        (20, BatteryStatus.LOW),
        (49.9, BatteryStatus.LOW),
        (50, BatteryStatus.OK),
        (100, BatteryStatus.OK),
    ],
)
def test_classify_boundaries(soc, status):
    assert classify(soc) is status
