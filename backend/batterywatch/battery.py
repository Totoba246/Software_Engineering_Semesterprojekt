"""The battery maths: corrected voltage, charge level in % and traffic-light status.

WHAT THIS FILE DOES
    Three small calculations, step by step for every measurement:

        node sends:  voltage_mV = 11276, current_mA = 551
          1. battery_voltage_mv()  ->  11277.1 mV   (add the shunt's voltage drop)
          2. state_of_charge()     ->  35 %         (volts -> percent via the curve)
          3. classify()            ->  "niedrig"    (percent -> red/yellow/green)

WHO USES IT
    - db.py calls step 1 when a measurement is saved (result stored in the DB).
    - api/main.py calls steps 2 and 3 every time the web page asks for data,
      so changed thresholds apply immediately without touching stored data.
    No network, no database here - "pure" functions, easy to test
    (tests/test_battery.py).

UNITS (important!)
    The nodes send MILLIvolts and MILLIamperes. Step 1 stays in mV/mA.
    The curve in step 2 is in VOLTS (the API divides by 1000 before calling it).
"""

from __future__ import annotations

from enum import Enum
from typing import Sequence


class BatteryStatus(str, Enum):
    """The four possible states. The text values are what the API/web page receive."""

    OK = "ok"                # green:  >= 50 %
    LOW = "niedrig"          # yellow: 20 - 49 %
    CRITICAL = "krit"        # red:    < 20 %
    UNKNOWN = "unbekannt"    # grey:   no valid measurement yet


def battery_voltage_mv(voltage_mv: float, current_ma: float, shunt_resistance_ohm: float = 0.002) -> float:
    """Battery terminal voltage from the TrafficNode measurement.

    The node measures the voltage behind a shunt resistor, so the voltage drop
    across the shunt has to be added back::

        U_bat = R_shunt * I_bat + U_measured
        U_bat = 0.002 Ohm * I_measured + U_measured

    Units: mA * Ohm = mV, so the result is in mV like the inputs.
    Example: 11276 mV + 0.002 Ohm * 551 mA = 11276 + 1.102 = 11277.102 mV
    """
    return voltage_mv + shunt_resistance_ohm * current_ma


def state_of_charge(battery_voltage_v: float | None, curve: Sequence[tuple[float, float]]) -> float | None:
    """Map a battery voltage (in VOLTS) to a state of charge (0-100 %).

    ``curve`` is a list of ``(volts, percent)`` points sorted by volts; values
    in between are interpolated linearly, values outside are clamped.

    Example with the default curve [(10.5, 0), (12.7, 100)]:
        10.5 V -> 0 %,  11.6 V -> 50 % (halfway),  12.7 V -> 100 %,
        9.0 V -> 0 % (clamped),  14.0 V -> 100 % (clamped)
    """
    if battery_voltage_v is None:            # no measurement -> no percentage
        return None
    if battery_voltage_v <= curve[0][0]:     # below the lowest point -> lowest %
        return float(curve[0][1])
    if battery_voltage_v >= curve[-1][0]:    # above the highest point -> highest %
        return float(curve[-1][1])
    # Find the two points the voltage lies between and draw a straight line.
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


def voltage_for_soc(soc_percent: float, curve: Sequence[tuple[float, float]]) -> float:
    """Inverse of ``state_of_charge``: the battery voltage (V) at a given charge level.

    Used for the prediction, e.g. "at which voltage is the battery critical (20 %)?"
    """
    if soc_percent <= curve[0][1]:
        return float(curve[0][0])
    if soc_percent >= curve[-1][1]:
        return float(curve[-1][0])
    for (v0, p0), (v1, p1) in zip(curve, curve[1:]):
        if p0 <= soc_percent <= p1:
            return v0 + (soc_percent - p0) * (v1 - v0) / (p1 - p0)
    raise AssertionError("unreachable: curve must be sorted")


def hours_until(voltage_now_v: float, target_v: float, trend_v_per_day: float | None) -> float | None:
    """Simple linear estimate: in how many hours does the voltage reach ``target_v``?

    0 if the target is already reached (also without a trend), None if the
    voltage isn't falling (no estimate possible). Deliberately simple
    (F04 "Wechselprognose", first version): a straight line through the trend
    of the last 72 hours.
    """
    if voltage_now_v <= target_v:
        return 0.0
    if trend_v_per_day is None or trend_v_per_day >= -0.005:  # flat or rising
        return None
    return (voltage_now_v - target_v) / -trend_v_per_day * 24
