"""Battery domain logic: voltage correction, state of charge and status rules.

Pure functions without I/O, so they can be unit tested in isolation.
"""

from __future__ import annotations

from enum import Enum
from typing import Sequence


class BatteryStatus(str, Enum):
    OK = "ok"
    LOW = "niedrig"
    CRITICAL = "krit"
    UNKNOWN = "unbekannt"


def battery_voltage_mv(voltage_mv: float, current_ma: float, shunt_resistance_ohm: float = 0.002) -> float:
    """Battery terminal voltage from the TrafficNode measurement.

    The node measures the voltage behind a shunt resistor, so the voltage drop
    across the shunt has to be added back::

        U_bat = R_shunt * I_bat + U_measured
        U_bat = 0.002 Ohm * I_measured + U_measured

    Units: mA * Ohm = mV, so the result is in mV like the inputs.
    """
    return voltage_mv + shunt_resistance_ohm * current_ma


def state_of_charge(battery_voltage_v: float | None, curve: Sequence[tuple[float, float]]) -> float | None:
    """Map a battery voltage (V) to a state of charge (0-100 %).

    ``curve`` is a list of ``(volts, percent)`` points sorted by volts; values
    in between are interpolated linearly, values outside are clamped.
    """
    if battery_voltage_v is None:
        return None
    if battery_voltage_v <= curve[0][0]:
        return float(curve[0][1])
    if battery_voltage_v >= curve[-1][0]:
        return float(curve[-1][1])
    for (v0, p0), (v1, p1) in zip(curve, curve[1:]):
        if v0 <= battery_voltage_v <= v1:
            return p0 + (battery_voltage_v - v0) * (p1 - p0) / (v1 - v0)
    raise AssertionError("unreachable: curve must be sorted")


def classify(soc_percent: float | None, critical_below: float = 20, low_below: float = 50) -> BatteryStatus:
    """Status rule: < 20 % critical, < 50 % low, otherwise ok (thresholds configurable)."""
    if soc_percent is None:
        return BatteryStatus.UNKNOWN
    if soc_percent < critical_below:
        return BatteryStatus.CRITICAL
    if soc_percent < low_below:
        return BatteryStatus.LOW
    return BatteryStatus.OK
