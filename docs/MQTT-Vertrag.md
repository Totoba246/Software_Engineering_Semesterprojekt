# MQTT-Vertrag – TrafficNode → BatteryWatch

Dieser Vertrag beschreibt, welche Nachrichten der Collection-Service (ADR-10) annimmt.
Umgesetzt und getestet in `backend/batterywatch/contract.py` bzw. `backend/tests/test_contract.py`.

## Topic

Live-Broker `mqtt.ti-labs.ai:8883` (TLS):

```
traffic-nodes/<device_id>/measurements          z. B. traffic-nodes/101/measurements
```

Ältere Aufzeichnungen (`docs/samples/…csv`) nutzen noch dieses Format, es wird weiterhin angenommen:

```
traffic-device/<tenant>/<device_type>/<device_id>/status
```

| Teil | Beispiel | Bedeutung |
|---|---|---|
| `device_id` | `101`, `TSN-002` | eindeutige Geräte-ID (Primärschlüssel in `devices`) |
| `tenant` | `dieringer-stark` | Betreiber (nur altes Format, sonst leer) |
| `device_type` | `trafficnode` | Art der Telemetriebox (neues Format: immer `trafficnode`) |

Erlaubte Zeichen je Teil: `A–Z a–z 0–9 _ . -`, max. 64 Zeichen.
Der Collector abonniert `traffic-nodes/+/measurements` und `traffic-device/+/+/+/status`
(`COLLECTOR_MQTT_TOPIC`, kommagetrennt). Node 101 sendet derzeit alle **15 Minuten** mit QoS 0.

## Payload (JSON)

```json
{
  "current_mA": 551.0,
  "voltage_mV": 11276.0,
  "temperature_C": 17.0,
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
| `temperature_C` | Zahl/null | – | −60 … 150 |
| `lat`, `lon` | Zahl/null | – | beide gesetzt oder beide `null`; `0/0` gilt als „kein GPS-Fix“ |
| `altitude_m` | Zahl/null | – | −500 … 10 000 |
| `satellites` | Ganzzahl/null | – | 0 … 100 |
| `time` | String/Zahl/null | – | ISO 8601 (ohne Zeitzone = UTC) oder Unix-Zeit in s bzw. ms; `null` → Empfangszeit |

- Unbekannte Zusatzfelder (z. B. `power_W`) werden ignoriert.
- `NaN`/`Infinity` sind ungültig.
- `voltage_mV = 0` wird abgelehnt: Die TrafficNode wird aus der gemessenen Batterie versorgt,
  0 V kann also kein echter Messwert sein (siehe `docs/samples/sample_msg.json` – so sieht
  eine unkonfigurierte Node aus).
- Über 60 V ist ein Lesefehler. Live beobachtet am 05.11.2026 bei Node 101:
  `"current_mA": -1.25, "voltage_mV": 5368709120` (= 1,25 · 2³²) – vermutlich kein Akku
  angeschlossen bzw. Sensor liefert keinen Wert. Solche Nachrichten werden verworfen.

## Verhalten des Collectors

| Fall | Verhalten |
|---|---|
| jede Nachricht | wird mit Ergebnis (gespeichert/verworfen + Grund) in `raw_messages` protokolliert |
| gültiges Topic | Gerät wird bei Bedarf in `devices` angelegt – auch wenn die Werte ungültig sind |
| gültige Nachricht | Messwert in `measurements` gespeichert |
| gleiche `device_id` + gleicher Zeitstempel | Duplikat (z. B. QoS-1-Wiederholung) → ignoriert |
| ungültiges Topic / JSON / Feld | **kein Messwert** (ADR-10); Grund steht im Log, in `raw_messages` und im Frontend |
| Datenbank kurz weg | Verbindung wird neu aufgebaut |
| Broker kurz weg | paho verbindet neu und abonniert erneut; persistente Session (`clean_session=false`) |
| Collector kurz weg | QoS-0-Nachrichten (Node 101) aus dieser Zeit gehen verloren – bei 15-Minuten-Takt meist keine oder eine |

Beim Speichern wird zusätzlich die Batteriespannung berechnet (siehe [Statusregeln](Statusregeln.md)):

```
U_bat = R_shunt · I_mess + U_mess = 0,002 Ω · I_mess + U_mess
```
