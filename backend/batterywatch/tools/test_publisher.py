"""Test publisher (A05): pretends to be traffic light nodes and sends FAKE messages.

WHY?
    Real nodes send rarely (node 101: every 15 min) and currently only garbage
    values. With this script we can test everything right away:
        this script --MQTT--> broker --> collector --> database --> API --> web page
    If fake devices SIM-001, SIM-002, ... show up on the web page, the whole
    chain works.

WHERE DOES IT SEND TO?
    The broker given by MQTT_HOST / MQTT_PORT (or --host / --port). In Docker
    that is our own test broker "mqtt" (container "publisher", docker-compose.yml).
    NEVER run it against the shared course broker mqtt.ti-labs.ai - other groups
    would receive our fake data.

Stands in for real nodes (only node 101 is sending at the moment) and lets us test
the complete path  publisher -> broker -> collector -> DB -> API -> UI.
Topic: traffic-nodes/<device_id>/measurements, like the live broker.
Only use it against our own broker, never against the shared live broker.

Modes::

    # simulate 6 nodes; first publish 3 days of history (every 15 min), then one message per node every 10 s
    python -m batterywatch.tools.test_publisher simulate --devices 6 --backfill-hours 72 --interval 10

    # 30 days of history written directly into the DB ($DATABASE_URL), then live over MQTT
    python -m batterywatch.tools.test_publisher simulate --backfill-hours 720 --backfill-direct --interval 10

    # one message per simulated node, then exit (smoke test)
    python -m batterywatch.tools.test_publisher simulate --once

    # also send every 20th message deliberately broken (tests the rejection path)
    python -m batterywatch.tools.test_publisher --invalid-every 20 simulate

    # replay the recorded sample data over MQTT (as fast as possible, moved to "now")
    python -m batterywatch.tools.test_publisher replay ../docs/samples/traffic_devices_signals.csv --shift-to-now

Broker settings come from MQTT_HOST / MQTT_PORT / MQTT_USERNAME / MQTT_PASSWORD / MQTT_TLS
(or --host / --port).
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import paho.mqtt.client as mqtt

from ..config import get_settings
from ..contract import Measurement, build_payload, build_topic
from ..db import MeasurementStore, ensure_schema
from .samples import read_sample_csv, shift_to

log = logging.getLogger("batterywatch.publisher")
BERLIN = ZoneInfo("Europe/Berlin")

# Sites for simulated devices (around the location of the recorded node TSN-002).
SITES = [
    ("Rottweil", 48.168, 8.628),
    ("Villingen-Schwenningen", 48.062, 8.493),
    ("Tuttlingen", 47.985, 8.818),
    ("Oberndorf am Neckar", 48.291, 8.574),
    ("Spaichingen", 48.075, 8.735),
    ("Schramberg", 48.225, 8.385),
    ("Balingen", 48.274, 8.851),
    ("Sulz am Neckar", 48.362, 8.632),
]


@dataclass
class SimulatedNode:
    """Very small battery model, tuned to look like the recorded TSN-002 data.

    - Load current: ~0.63 A during the day, ~0.52 A at night (the traffic light
      dims at night -> voltage plateaus), plus noise and occasional spikes.
    - Open-circuit voltage falls linearly (~0.11 V/day in the recordings); when the
      battery is empty a technician swaps it (sawtooth over time).
    - Terminal voltage sags under load via an internal resistance.
    - The node measures behind a 2 mOhm shunt: U_measured = U_bat - 0.002 Ohm * I.

    The charge level is anchored at ``anchor`` (start of the script), so the
    devices show a spread of states "now", however much history is backfilled.
    """

    device_id: str
    lat: float
    lon: float
    altitude_m: float
    ocv_at_anchor_v: float
    drain_v_per_day: float
    anchor: datetime
    internal_resistance_ohm: float = 0.5
    shunt_ohm: float = 0.002
    empty_v: float = 10.75
    full_v: float = 12.95

    def open_circuit_voltage(self, at: datetime) -> float:
        days = (at - self.anchor).total_seconds() / 86400
        span = self.full_v - self.empty_v
        ocv = self.ocv_at_anchor_v - self.drain_v_per_day * days
        # wrap around = battery swapped (going forward) / previous battery (going back)
        return self.empty_v + (ocv - self.empty_v) % span

    def sample(self, at: datetime, rng: random.Random) -> dict:
        ocv = self.open_circuit_voltage(at)

        hour = at.astimezone(BERLIN).hour
        night = hour >= 21 or hour < 6
        current_a = (0.52 if night else 0.63) + rng.gauss(0, 0.035)
        if rng.random() < 0.03:
            current_a += rng.uniform(0.1, 0.2)  # short load spike
        current_a = max(current_a, 0.05)

        u_bat = ocv - self.internal_resistance_ohm * current_a + rng.gauss(0, 0.03)
        u_measured = u_bat - self.shunt_ohm * current_a
        return {
            "current_ma": current_a * 1000,
            "voltage_mv": u_measured * 1000,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "altitude_m": self.altitude_m,
            "satellites": rng.randint(6, 12),
            # daily temperature cycle, warmest around 15:00
            "temperature_c": 12 + 6 * math.sin((hour - 9) / 24 * 2 * math.pi) + rng.gauss(0, 0.3),
        }


def make_nodes(count: int, seed: int, anchor: datetime) -> list[SimulatedNode]:
    rng = random.Random(seed)
    nodes = []
    for i in range(count):
        _, lat, lon = SITES[i % len(SITES)]
        nodes.append(
            SimulatedNode(
                device_id=f"SIM-{i + 1:03d}",
                lat=lat + rng.uniform(-0.01, 0.01),
                lon=lon + rng.uniform(-0.015, 0.015),
                altitude_m=round(rng.uniform(550, 750), 1),
                # spread over the whole range so all status colours appear
                ocv_at_anchor_v=10.95 + (12.9 - 10.95) * ((0.2 + i * 0.61803) % 1),
                drain_v_per_day=rng.uniform(0.08, 0.16),
                anchor=anchor,
            )
        )
    return nodes


def connect(args) -> mqtt.Client:
    settings = get_settings()
    host = args.host or settings.mqtt_host
    port = args.port or settings.mqtt_port
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"batterywatch-testpublisher-{random.randrange(1 << 30)}")
    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
    if settings.mqtt_tls:
        client.tls_set(ca_certs=settings.mqtt_ca_file, cert_reqs=ssl.CERT_REQUIRED)
    log.info("connecting to %s:%s", host, port)
    client.connect(host, port, keepalive=60)
    client.loop_start()
    return client


class Publisher:
    def __init__(self, client: mqtt.Client, invalid_every: int = 0, dry_run: bool = False, rate: float = 0):
        self.client = client
        self.invalid_every = invalid_every
        self.dry_run = dry_run
        # Max messages per second. Brokers drop QoS 1 messages when a subscriber's
        # queue overflows (Mosquitto default: 1000), so bulk sends must be paced.
        self.rate = rate
        self._next_at = time.monotonic()
        self.sent = 0
        self.invalid = 0

    def _pace(self) -> None:
        if not self.rate:
            return
        now = time.monotonic()
        if self._next_at > now:
            time.sleep(self._next_at - now)
        self._next_at = max(now, self._next_at) + 1 / self.rate

    def send(self, topic: str, payload: str) -> None:
        self._pace()
        self.sent += 1
        if self.invalid_every and self.sent % self.invalid_every == 0:
            payload = self._break(payload)
            self.invalid += 1
        if self.dry_run:
            print(topic, payload)
            return
        info = self.client.publish(topic, payload, qos=1)
        if self.sent % 200 == 0:
            info.wait_for_publish(timeout=10)  # simple back-pressure for bulk sends

    def _break(self, payload: str) -> str:
        data = json.loads(payload)
        kind = self.invalid % 4
        if kind == 0:
            data.pop("voltage_mV")  # required field missing
        elif kind == 1:
            data["current_mA"] = "viel"  # wrong type
        elif kind == 2:
            # read error seen live from node 101 (1.25 * 2^32)
            data.update(current_mA=-1.25, voltage_mV=5368709120.0)
        else:
            return "{not json"
        return json.dumps(data)

    def finish(self) -> None:
        if not self.dry_run:
            time.sleep(0.5)
            self.client.loop_stop()
            self.client.disconnect()
        log.info("sent %d messages (%d deliberately invalid)", self.sent, self.invalid)


def run_simulate(args, pub: Publisher) -> None:
    rng = random.Random(args.seed)
    # Round "now" down to the --step grid (e.g. full quarter hours). Then a restart
    # produces the SAME history timestamps, which the database skips as duplicates,
    # instead of piling up another 30 days of slightly shifted fake data.
    now = datetime.fromtimestamp(time.time() // args.step * args.step, timezone.utc)
    nodes = make_nodes(args.devices, args.seed, anchor=now)

    def publish_all(at: datetime) -> None:
        for node in nodes:
            s = node.sample(at, rng)
            payload = build_payload(
                s["current_ma"], s["voltage_mv"], at, s["lat"], s["lon"], s["altitude_m"], s["satellites"],
                s["temperature_c"],
            )
            pub.send(build_topic(node.device_id), payload)

    if args.backfill_hours:
        steps = int(args.backfill_hours * 3600 // args.step)
        times = [now - timedelta(seconds=k * args.step) for k in range(steps, 0, -1)]
        if args.backfill_direct:
            backfill_into_database(nodes, times, rng)
        else:
            log.info(
                "backfilling %s h via MQTT: %d messages, ~%.0f s at %s msg/s",
                args.backfill_hours, steps * len(nodes), steps * len(nodes) / (args.rate or 1e9), args.rate or "max",
            )
            for at in times:
                publish_all(at)

    while True:
        publish_all(datetime.now(timezone.utc).replace(microsecond=0))
        log.info("published live sample for %d nodes", len(nodes))
        if args.once:
            return
        time.sleep(args.interval)


def backfill_into_database(nodes: list[SimulatedNode], times: list[datetime], rng: random.Random) -> None:
    """Write simulated history straight into the database (much faster than MQTT)."""
    settings = get_settings()
    store = MeasurementStore(settings.database_url, settings.shunt_resistance_ohm)
    ensure_schema(store.conn)

    def rows():
        for at in times:
            for node in nodes:
                s = node.sample(at, rng)
                yield Measurement(
                    device_id=node.device_id, tenant=None, device_type="trafficnode", measured_at=at,
                    current_ma=round(s["current_ma"], 2), voltage_mv=round(s["voltage_mv"], 2),
                    latitude=s["lat"], longitude=s["lon"], altitude_m=s["altitude_m"], satellites=s["satellites"],
                    temperature_c=round(s["temperature_c"], 2),
                )

    inserted = store.save_many(rows(), source="import")
    store.close()
    log.info("backfilled %d measurements directly into the database", inserted)


def run_replay(args, pub: Publisher) -> None:
    rows = read_sample_csv(args.file, device_id=args.device_id)
    if args.shift_to_now:
        rows = list(shift_to(rows, datetime.now(timezone.utc)))
    log.info("replaying %d rows (speed=%s)", len(rows), args.speed or "max")
    previous = None
    for m in rows:
        if args.speed and previous is not None:
            time.sleep(max(0.0, (m.measured_at - previous).total_seconds() / args.speed))
        previous = m.measured_at
        payload = build_payload(
            m.current_ma, m.voltage_mv, m.measured_at, m.latitude, m.longitude, m.altitude_m, m.satellites
        )
        pub.send(build_topic(m.device_id), payload)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", help="MQTT host (default: $MQTT_HOST)")
    parser.add_argument("--port", type=int, help="MQTT port (default: $MQTT_PORT)")
    parser.add_argument("--invalid-every", type=int, default=0, metavar="N", help="break every N-th message")
    parser.add_argument("--dry-run", action="store_true", help="print messages instead of publishing")
    parser.add_argument("--rate", type=float, default=300, help="max messages per second (0 = unlimited)")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_sim = sub.add_parser("simulate", help="simulated nodes with a simple battery model")
    p_sim.add_argument("--devices", type=int, default=6)
    p_sim.add_argument("--interval", type=float, default=900, help="seconds between live messages (node 101: 900)")
    p_sim.add_argument("--backfill-hours", type=float, default=0, help="first publish this much history")
    p_sim.add_argument("--step", type=int, default=900, help="seconds between backfilled messages")
    p_sim.add_argument(
        "--backfill-direct", action="store_true",
        help="write the backfill directly into $DATABASE_URL instead of publishing it (fast, for long histories)",
    )
    p_sim.add_argument("--once", action="store_true", help="publish one live message per node and exit")
    p_sim.add_argument("--seed", type=int, default=42)

    p_rep = sub.add_parser("replay", help="publish recorded sample data")
    p_rep.add_argument("file")
    p_rep.add_argument("--device-id", help="publish under this device id instead of the one in the file")
    p_rep.add_argument("--shift-to-now", action="store_true", help="move timestamps so the data ends today")
    p_rep.add_argument("--speed", type=float, default=0, help="time factor, e.g. 600 = 10 min per second; 0 = max")

    args = parser.parse_args(argv)
    client = None if args.dry_run else connect(args)
    pub = Publisher(client, invalid_every=args.invalid_every, dry_run=args.dry_run, rate=args.rate)
    try:
        if args.mode == "simulate":
            run_simulate(args, pub)
        else:
            run_replay(args, pub)
    except KeyboardInterrupt:
        pass
    finally:
        pub.finish()
    return 0


if __name__ == "__main__":
    sys.exit(main())
