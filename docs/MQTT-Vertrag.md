# MQTT-Vertrag – TrafficNode → BatteryWatch

Dieser Vertrag beschreibt, welche Nachrichten der Collection-Service (ADR-10) annimmt.
Umgesetzt und getestet in `backend/batterywatch/contract.py` bzw. `backend/tests/test_contract.py`.

## Topic

```
traffic-device/<tenant>/<device_type>/<device_id>/status
```

| Teil | Beispiel | Bedeutung |
|---|---|---|
| `tenant` | `dieringer-stark` | Betreiber |
| `device_type` | `trafficnode` | Art der Telemetriebox |
| `device_id` | `TSN-002` | eindeutige Geräte-ID (Primärschlüssel in `devices`) |

Erlaubte Zeichen je Teil: `A–Z a–z 0–9 _ . -`, max. 64 Zeichen.
Der Collector abonniert `traffic-device/+/+/+/status` mit **QoS 1**.

## Payload (JSON)

```json
{
  "current_mA": 551.0,
  "voltage_mV": 11276.0,
  "lat": 48.201157,
  "lon": 8.649726,
  "altitude_m": 609.6,
  "satellites": 7,
  "time": "2026-03-19T08:50:50Z"
}
```

| Feld | Typ | Pflicht | Regel |
|---|---|---|---|
| `current_mA` | Zahl | ✅ | −100 000 … 100 000 |
| `voltage_mV` | Zahl | ✅ | > 0 … 60 000 (gemessen **hinter** dem Shunt) |
| `lat`, `lon` | Zahl/null | – | beide gesetzt oder beide `null`; `0/0` gilt als „kein GPS-Fix“ |
| `altitude_m` | Zahl/null | – | −500 … 10 000 |
| `satellites` | Ganzzahl/null | – | 0 … 100 |
| `time` | String/Zahl/null | – | ISO 8601 (ohne Zeitzone = UTC) oder Unix-Zeit in s bzw. ms; `null` → Empfangszeit |

- Unbekannte Zusatzfelder (z. B. `power_W`) werden ignoriert.
- `NaN`/`Infinity` sind ungültig.
- `voltage_mV = 0` wird abgelehnt: Die TrafficNode wird aus der gemessenen Batterie versorgt,
  0 V kann also kein echter Messwert sein (siehe `docs/samples/sample_msg.json` – so sieht
  eine unkonfigurierte Node aus).

## Verhalten des Collectors

| Fall | Verhalten |
|---|---|
| gültige Nachricht | Gerät wird bei Bedarf in `devices` angelegt, Messwert in `measurements` gespeichert |
| gleiche `device_id` + gleicher Zeitstempel | Duplikat (z. B. QoS-1-Wiederholung) → ignoriert |
| ungültiges Topic / JSON / Feld | **verworfen und geloggt**, nicht gespeichert (ADR-10) |
| Datenbank kurz weg | Verbindung wird neu aufgebaut |
| Broker kurz weg | paho verbindet neu und abonniert erneut; persistente Session (`clean_session=false`) |

Beim Speichern wird zusätzlich die Batteriespannung berechnet (siehe [Statusregeln](Statusregeln.md)):

```
U_bat = R_shunt · I_mess + U_mess = 0,002 Ω · I_mess + U_mess
```
