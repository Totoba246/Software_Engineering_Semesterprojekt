"""Tests for the plausibility report (tools/plausibility.py)."""

from datetime import datetime, timedelta, timezone

from batterywatch.contract import Measurement
from batterywatch.tools.plausibility import Rules, judge, report

START = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)


def m(t: datetime, voltage_mv: float, current_ma: float = 600.0) -> Measurement:
    return Measurement("101", None, "trafficnode", t, current_ma, voltage_mv, None, None, None, None)


def cycle(start: datetime, days: int, v_start: float, v_end: float, step=timedelta(minutes=15)):
    n = int(days * 86400 / step.total_seconds())
    return [m(start + k * step, v_start + (v_end - v_start) * k / n) for k in range(n)]


def test_judge():
    r = Rules()
    assert judge(m(START, 11_800), r) == "ok"
    assert judge(m(START, 5_368_709_120, -1.25), r) == "unmöglich"  # node 101's read error
    assert judge(m(START, 0), r) == "unmöglich"
    assert judge(m(START, 12_710, -290), r) == "ok"  # node 101 reports discharge as negative
    assert judge(m(START, 11_800, 6_000), r) == "auffällig"  # 6 A: far more than a traffic light draws
    assert judge(m(START, 3_000), r) == "auffällig"  # possible, but not a 12 V battery


def test_report_finds_cycles_swap_and_cutoff():
    first = cycle(START, 5, 12_600, 10_700)
    # battery swapped during a 6 h gap
    second = cycle(first[-1].measured_at + timedelta(hours=6), 5, 12_600, 10_800)
    garbage_start = second[-1].measured_at + timedelta(minutes=15)
    garbage = [m(garbage_start + k * timedelta(minutes=15), 5_368_709_120, -1.25) for k in range(200)]
    text = report(first + second + garbage)

    assert "Entladezyklen erkannt: 2" in text
    assert "während der Lücke" in text
    assert "Wert hängt: 200x exakt 5368709120 mV" in text
    assert "Danach nur noch nicht plausible Werte: 200 Stück" in text
    last_ok = second[-1].measured_at
    assert f"--to {last_ok.isoformat(timespec='seconds')}" in text


def test_report_all_good():
    text = report(cycle(START, 2, 12_600, 12_300))
    assert "Bis zum Ende überwiegend plausible Werte." in text
    assert "Entladezyklen erkannt: 1" in text


def test_report_nothing_plausible():
    assert "KEIN einziger plausibler Messwert" in report([m(START, 5_368_709_120, -1.25)])


def test_report_shows_values_and_negative_current_like_node_101():
    rows = [m(START + timedelta(minutes=15 * k), 12_700 - k, -300) for k in range(96)]
    text = report(rows)
    assert "100 % negativ  -> Entladung wird NEGATIV gemeldet" in text
    assert "12.70" in text  # voltage visible in the day table
    assert "Bis zum Ende überwiegend plausible Werte." in text
