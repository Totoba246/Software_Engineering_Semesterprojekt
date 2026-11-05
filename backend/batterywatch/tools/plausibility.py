"""Plausibility report: which measurements make sense, and from when on they don't.

WHAT THIS FILE DOES
    Looks at a list of measurements (e.g. everything in the course's history
    database) WITHOUT changing anything, and prints a text report:
      1. overview per device (time range, number of readings, typical interval)
      2. one line per day: how many readings were plausible, voltage min/typical/max
      3. events: battery swaps, gaps, frozen values, first implausible values
      4. verdict: "from <time> on no plausible measurements"

    Run on the server:  ./deploy/import-history.sh --check
    (= import_data history --check, see import_data.py)

HOW A SINGLE READING IS JUDGED (all values in mV / mA, like the nodes send)
    "unmöglich"  outside the hard limits of the MQTT contract
                 (voltage <= 0 or > 60 V, current beyond +-100 A) -> never imported
    "auffällig"  physically possible, but not what a 12 V traffic light battery
                 does: voltage outside 9-15 V or current outside 0-5 A
                 (e.g. -1.25 mA = no load / sensor not reading)
    "ok"         everything else
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from ..contract import Measurement, within_limits

BERLIN = ZoneInfo("Europe/Berlin")  # days are cut at midnight German time


@dataclass(frozen=True)
class Rules:
    """Window of believable values for a 12 V battery (adjustable via command line)."""

    v_min_mv: float = 9_000      # a 12 V lead battery is deeply discharged below ~10.5 V; 9 V leaves room
    v_max_mv: float = 15_000     # even while charging, a 12 V battery stays below ~14.8 V
    i_min_ma: float = 0          # negative = current flowing the wrong way / sensor offset
    i_max_ma: float = 5_000      # the traffic light draws ~0.5-0.7 A
    swap_jump_mv: float = 500    # voltage rising this much (also across a gap) = battery swapped
    swap_window: timedelta = timedelta(hours=12)  # compare readings up to 12 h before/after
    gap: timedelta = timedelta(hours=1)  # no reading for longer = gap
    frozen_count: int = 12       # this many identical readings in a row = value "stuck"


def judge(m: Measurement, rules: Rules) -> str:
    """Return "unmöglich", "auffällig" or "ok" for one reading."""
    if not within_limits(m.voltage_mv, m.current_ma):
        return "unmöglich"
    if not (rules.v_min_mv <= m.voltage_mv <= rules.v_max_mv and rules.i_min_ma <= m.current_ma <= rules.i_max_ma):
        return "auffällig"
    return "ok"


def _fmt_t(t: datetime) -> str:
    return t.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M")


def _raw(x: float) -> str:
    """A raw value without scientific notation: 5368709120 instead of 5.36871e+09."""
    return f"{x:.0f}" if abs(x) >= 1e6 else f"{x:g}"


def _v(mv: float) -> str:
    """mV -> '11.28' (volts), or the raw number if it's absurd."""
    return f"{mv / 1000:.2f}" if abs(mv) < 1e6 else f"{mv:.0f}mV"


def _device_report(device_id: str, rows: list[Measurement], rules: Rules) -> list[str]:
    rows = sorted(rows, key=lambda m: m.measured_at)
    verdicts = [judge(m, rules) for m in rows]
    counts = Counter(verdicts)
    steps = [(b.measured_at - a.measured_at).total_seconds() for a, b in zip(rows, rows[1:])]
    out = [
        f"=== Gerät {device_id} ===",
        f"Zeitraum:   {_fmt_t(rows[0].measured_at)} bis {_fmt_t(rows[-1].measured_at)} (deutsche Zeit)",
        f"Messwerte:  {len(rows)}  davon ok {counts['ok']}, auffällig {counts['auffällig']}, "
        f"unmöglich {counts['unmöglich']}",
        f"Takt:       typisch alle {median(steps) / 60:.1f} Min." if steps else "Takt:       -",
        "",
        "Tag         Anzahl  ok%   U min / typisch / max [V]   I typisch [A]  Bemerkung",
    ]

    # --- per day -------------------------------------------------------------
    by_day: dict[str, list[tuple[Measurement, str]]] = defaultdict(list)
    for m, v in zip(rows, verdicts):
        by_day[m.measured_at.astimezone(BERLIN).strftime("%Y-%m-%d")].append((m, v))
    day_ok_share = {}
    for day, items in sorted(by_day.items()):
        ok = [m for m, v in items if v == "ok"]
        share = len(ok) / len(items)
        day_ok_share[day] = share
        if ok:
            volts = [m.voltage_mv for m in ok]
            v_txt = f"{_v(min(volts)):>6} / {_v(median(volts)):>6} / {_v(max(volts)):>6}"
            i_txt = f"{median(m.current_ma for m in ok) / 1000:6.3f}"
        else:
            v_txt, i_txt = f"{'-':>6} / {'-':>6} / {'-':>6}", f"{'-':>6}"
        bad = Counter(v for _, v in items if v != "ok")
        note = ", ".join(f"{n}x {k}" for k, n in bad.items())
        out.append(f"{day}  {len(items):6d}  {share * 100:4.0f}  {v_txt}      {i_txt}         {note}")

    # --- events --------------------------------------------------------------
    events = []
    ok_rows = [m for m, v in zip(rows, verdicts) if v == "ok"]
    # battery swaps: the next ~20 plausible readings are clearly above the previous ~20
    # (within 12 h, so a swap during a gap in the data is found as well)
    swaps = []
    for i, m in enumerate(ok_rows):
        before = [x.voltage_mv for x in ok_rows[max(0, i - 20):i] if m.measured_at - x.measured_at <= rules.swap_window]
        after = [x.voltage_mv for x in ok_rows[i:i + 20] if x.measured_at - m.measured_at <= rules.swap_window]
        if len(before) >= 3 and len(after) >= 3 and median(after) - median(before) >= rules.swap_jump_mv:
            jump = (m.measured_at, median(before), median(after), i)
            if not swaps or m.measured_at - swaps[-1][0] > timedelta(hours=6):
                swaps.append(jump)
            elif jump[2] - jump[1] > swaps[-1][2] - swaps[-1][1]:
                swaps[-1] = jump  # same swap, but a bigger jump -> closer to the real moment
    swap_texts = []
    for t, u_before, u_after, i in swaps:
        # Averaging smears the exact moment. If there is a gap right there, the
        # battery was most likely swapped while the node wasn't sending.
        window = ok_rows[max(0, i - 20):i + 20]
        gap = next(((a, b) for a, b in zip(window, window[1:]) if b.measured_at - a.measured_at > rules.gap), None)
        when = (f"während der Lücke {_fmt_t(gap[0].measured_at)} - {_fmt_t(gap[1].measured_at)}" if gap
                else f"um {_fmt_t(t)}")
        swap_texts.append(when)
        events.append(f"{_fmt_t(gap[1].measured_at if gap else t)}  Spannung springt {_v(u_before)} -> "
                      f"{_v(u_after)} V {when} (Akkuwechsel / Laden?)")
    # gaps
    for a, b in zip(rows, rows[1:]):
        if b.measured_at - a.measured_at > rules.gap:
            hours = (b.measured_at - a.measured_at).total_seconds() / 3600
            events.append(f"{_fmt_t(a.measured_at)}  Lücke von {hours:.1f} Std. (nächster Wert {_fmt_t(b.measured_at)})")
    # frozen values
    run_start, run_len = 0, 1
    for i in range(1, len(rows) + 1):
        if i < len(rows) and rows[i].voltage_mv == rows[i - 1].voltage_mv:
            run_len += 1
            continue
        if run_len >= rules.frozen_count:
            events.append(f"{_fmt_t(rows[run_start].measured_at)}  Wert hängt: {run_len}x exakt "
                          f"{_raw(rows[run_start].voltage_mv)} mV bis {_fmt_t(rows[i - 1].measured_at)}")
        run_start, run_len = i, 1
    # first implausible readings + the most common bad values
    first_bad = next(((m, v) for m, v in zip(rows, verdicts) if v != "ok"), None)
    if first_bad:
        m, v = first_bad
        events.append(f"{_fmt_t(m.measured_at)}  erster {v}er Wert: U={_raw(m.voltage_mv)} mV, I={_raw(m.current_ma)} mA")
    # sort by real time (the text starts with the German date, which doesn't sort correctly)
    events.sort(key=lambda e: datetime.strptime(e[:16], "%d.%m.%Y %H:%M"))
    common = Counter((m.voltage_mv, m.current_ma) for m, v in zip(rows, verdicts) if v != "ok").most_common(3)
    events += [f"häufiger Problemwert: U={_raw(u)} mV, I={_raw(i)} mA ({n}x)" for (u, i), n in common]
    out += ["", "Ereignisse:"] + ([f"  {e}" for e in events] or ["  keine"])

    # --- verdict -------------------------------------------------------------
    out += ["", "Ergebnis:"]
    if not ok_rows:
        out.append("  KEIN einziger plausibler Messwert.")
        return out
    out.append(f"  Entladezyklen erkannt: {len(swaps) + 1}"
               + (f" (Akkuwechsel {'; '.join(swap_texts)})" if swaps else ""))
    last_ok = ok_rows[-1]
    after_last_ok = [m for m in rows if m.measured_at > last_ok.measured_at]
    out.append(f"  Letzter plausibler Messwert: {_fmt_t(last_ok.measured_at)} "
               f"(U={_v(last_ok.voltage_mv)} V, I={last_ok.current_ma / 1000:.3f} A)")
    if after_last_ok:
        out.append(f"  Danach nur noch nicht plausible Werte: {len(after_last_ok)} Stück bis "
                   f"{_fmt_t(after_last_ok[-1].measured_at)}")
    # first day from which on every day is mostly bad
    days = sorted(day_ok_share)
    cut = None
    for d in reversed(days):
        if day_ok_share[d] < 0.5:
            cut = d
        else:
            break
    if cut:
        out.append(f"  Ab {cut} ist an jedem Tag weniger als die Hälfte der Werte plausibel.")
    else:
        out.append("  Bis zum Ende überwiegend plausible Werte.")
    out.append(f"  Vorschlag Import nur bis dahin:  --to {last_ok.measured_at.isoformat(timespec='seconds')}")
    return out


def report(rows: list[Measurement], rules: Rules | None = None) -> str:
    """Full text report for all devices in ``rows``."""
    rules = rules or Rules()
    if not rows:
        return "Keine Messwerte gefunden."
    by_device: dict[str, list[Measurement]] = defaultdict(list)
    for m in rows:
        by_device[m.device_id].append(m)
    out = [
        "PLAUSIBILITÄTSPRÜFUNG",
        f"Regeln: ok = {rules.v_min_mv / 1000:g}-{rules.v_max_mv / 1000:g} V und "
        f"{rules.i_min_ma / 1000:g}-{rules.i_max_ma / 1000:g} A; unmöglich = <= 0 V oder > 60 V "
        "(wird nie importiert)",
        "",
    ]
    for device_id, items in sorted(by_device.items()):
        out += _device_report(device_id, items, rules) + [""]
    return "\n".join(out)
