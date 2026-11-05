# Statusregeln (F02) – vom Messwert zum Ampelstatus

Umgesetzt in `backend/batterywatch/battery.py`, getestet in `backend/tests/test_battery.py`.
Alle Zahlen sind über Umgebungsvariablen einstellbar (siehe `.env.example`).

## 1. Batteriespannung aus dem Messwert

Die TrafficNode misst die Spannung hinter einem Shunt-Widerstand. Der Spannungsabfall am
Shunt wird wieder addiert:

```
U_bat = R_shunt · I_bat + U_i
U_bat = 0,002 Ω · I_messung + U_messung        (mA · Ω = mV)
```

Beispiel TSN-002: 11 276 mV + 0,002 Ω · 551 mA = 11 277,1 mV.
Gespeichert werden Rohwerte **und** `battery_voltage_mv`, damit sich eine Korrektur später
nachrechnen lässt. Variable: `SHUNT_RESISTANCE_OHM`.

## 2. Glättung

Einzelwerte streuen um ca. ±0,15 V. Zusätzlich **dimmt die Ampel nachts** (ca. 21–6 Uhr):
Sie zieht dann weniger Strom (≈ 0,52 A statt ≈ 0,63 A), die Spannung unter Last steigt etwas
an – im Verlauf entstehen **Plateaus**. Das ist kein Messfehler und auch kein Nachladen.

Deshalb gilt als „aktuelle“ Spannung der **Mittelwert der letzten 60 Minuten** vor der letzten
Meldung (`SMOOTHING_MINUTES`). Der Trend in V/Tag wird über **72 Stunden** gerechnet
(drei volle Tag/Nacht-Zyklen), damit sich die Plateaus herausmitteln.
In der Verlaufsgrafik ist die Nacht grau hinterlegt.

## 3. Ladezustand (SoC)

Stückweise lineare Kennlinie Spannung → Prozent (`BATTERY_SOC_CURVE`).

> ⚠️ **Platzhalter:** Aktuell `10,5 V = 0 %` bis `12,7 V = 100 %` (linear, 12-V-Bleiakku unter Last).
> Batterietyp und Kennlinie müssen noch fachlich geprüft werden. Eine genauere Kennlinie wird
> ohne Codeänderung gesetzt, z. B. `BATTERY_SOC_CURVE=10.5:0,11.3:10,11.8:30,12.2:60,12.7:100`.

## 4. Status

| Status | Regel | Farbe |
|---|---|---|
| Kritisch | SoC < 20 % (`STATUS_CRITICAL_BELOW`) | rot |
| Niedrig | 20 % ≤ SoC < 50 % (`STATUS_LOW_BELOW`) | gelb |
| Gut | SoC ≥ 50 % | grün |
| Unbekannt | noch keine Messwerte | grau |

Zusätzlich: **Keine Meldung seit > 30 Minuten** (`STALE_AFTER_MINUTES`, Nodes senden alle
~3 Minuten) → „Letzte Meldung“ wird rot markiert. Der Akkustatus bezieht sich dann auf den
letzten bekannten Stand.

## Offene Punkte

- Kennlinie mit echtem Batterietyp/Datenblatt abgleichen.
- Schwellwerte mit dem Betreiber abstimmen (wie viel Vorlauf braucht ein Wechsel?).
- Vorwarnung/Benachrichtigung bei „kritisch“ (F02, nicht im MVP).
