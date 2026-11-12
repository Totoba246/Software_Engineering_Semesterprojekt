"""The COLLECTOR: listens to the MQTT broker and saves every node message (ADR-10).

WHAT THIS PROGRAM DOES, START TO END
    1. Connects to the database and creates the tables if needed.
    2. Connects to the MQTT broker
         - on the server: mqtt.ti-labs.ai port 8883, encrypted, user tinf25d-llv
         - in tests:      our own broker container "mqtt" port 1883
       (settings: MQTT_* environment variables, see config.py / .env)
    3. Subscribes to the topics, e.g. traffic-nodes/+/measurements
       ("+" = any node, so it receives traffic-nodes/101/measurements etc.).
    4. Then waits forever. For EVERY message the broker forwards:
         a) check it (contract.py)                 -> valid or rejected + reason
         b) save it (db.py)                        -> raw_messages (always)
                                                      + measurements (only if valid)
    If the broker or the database is briefly unreachable, it reconnects by itself.

    It opens NO port and has no web page - it only connects OUT.
    Watch what it does:  docker compose logs -f collector

RUN
    In Docker: the "collector" container (docker-compose.yml).
    By hand:   python -m batterywatch.collector   (runs __main__.py -> main() below)

"paho" is the MQTT library we use. It calls our ``on_...`` methods when
something happens (connected, message arrived, ...) - so-called "callbacks".
"""

from __future__ import annotations

import logging
import signal
import ssl
import sys
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from ..config import Settings, get_settings
from ..contract import ContractError, parse_message, parse_topic
from ..db import MeasurementStore, ensure_schema

log = logging.getLogger("batterywatch.collector")


class Collector:
    """Checks and stores messages; also counts what happened (``stats``)."""

    def __init__(self, settings: Settings, store: MeasurementStore):
        self.settings = settings
        self.store = store
        self.stats = {"stored": 0, "duplicate": 0, "rejected": 0}

    def handle_message(self, topic: str, payload: bytes) -> str:
        """Validate and store one message. Returns 'stored', 'duplicate' or 'rejected'.

        Every message is logged in raw_messages. Only valid ones become measurements
        (ADR-10: invalid values never reach the measurements/charts).
        """
        # MQTT delivers raw bytes; turn them into text for the log table.
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        device = measurement = error = None
        try:
            device = parse_topic(topic)       # which node? (from the topic)
            measurement = parse_message(topic, payload, received_at=datetime.now(timezone.utc))  # values OK?
        except ContractError as exc:
            # Not valid (e.g. voltage_mV = 5368709120): remember the reason, write a log line.
            error = str(exc)
            log.warning("rejected message on %s: %s | payload=%r", topic, exc, text[:300])
        # Save: message log always, measurement only if valid (see db.py).
        stored = self.store.save_message(topic, text, device, measurement, error)
        result = "rejected" if error else ("stored" if stored else "duplicate")
        if measurement is not None:
            log.debug("%s %s @ %s", result, measurement.device_id, measurement.measured_at.isoformat())
        self.stats[result] += 1
        total = sum(self.stats.values())
        if total % 100 == 0:  # a short summary every 100 messages
            log.info("processed %d messages: %s", total, self.stats)
        return result

    # --- paho callbacks ----------------------------------------------------
    # paho calls these methods itself; we never call them directly.

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Called when the connection to the broker is up (also after a reconnect)."""
        if reason_code.is_failure:
            log.error("MQTT connect failed: %s", reason_code)
            return
        # Subscribing here means we re-subscribe automatically after reconnects.
        client.subscribe([(t, 1) for t in self.settings.mqtt_topics])
        log.info(
            "connected to %s:%s, subscribing to %s",
            self.settings.mqtt_host,
            self.settings.mqtt_port,
            ", ".join(self.settings.mqtt_topics),
        )

    def on_subscribe(self, client, userdata, mid, reason_codes, properties=None):
        """Called when the broker answers our subscription (allowed or refused)."""
        for topic, rc in zip(self.settings.mqtt_topics, reason_codes):
            if rc.is_failure:
                # e.g. the broker's ACL does not allow this topic for our user
                log.error("broker refused subscription to %r: %s", topic, rc)
            else:
                log.info("subscription to %r confirmed (%s)", topic, rc)

    def on_connect_fail(self, client, userdata):
        """Called when a connection attempt fails; paho tries again by itself."""
        log.warning(
            "cannot reach MQTT broker %s:%s (DNS, firewall, TLS or credentials?) - retrying",
            self.settings.mqtt_host, self.settings.mqtt_port,
        )

    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Called when the connection drops (network hiccup, broker restart, ...)."""
        log.warning("MQTT disconnected (%s), paho will reconnect", reason_code)

    def on_message(self, client, userdata, msg):
        """Called for EVERY message the broker forwards to us."""
        try:
            self.handle_message(msg.topic, msg.payload)
        except Exception:  # never let one bad message kill the service
            log.exception("failed to process message on %s", msg.topic)


def build_client(settings: Settings, collector: Collector) -> mqtt.Client:
    """Create the MQTT connection object with login, encryption and our callbacks."""
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=settings.mqtt_client_id,
        # Persistent session: the broker keeps QoS 1 messages while we are offline.
        clean_session=False,
    )
    if settings.mqtt_username:  # login (course broker: user tinf25d-llv + password)
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
    if settings.mqtt_tls:  # encryption (port 8883); also checks the broker's certificate
        client.tls_set(ca_certs=settings.mqtt_ca_file, cert_reqs=ssl.CERT_REQUIRED)
    client.reconnect_delay_set(min_delay=1, max_delay=60)  # retry after 1 s, 2 s, 4 s ... max 60 s
    client.on_connect = collector.on_connect
    client.on_disconnect = collector.on_disconnect
    client.on_subscribe = collector.on_subscribe
    client.on_connect_fail = collector.on_connect_fail
    client.on_message = collector.on_message
    return client


def main() -> int:
    """Start the collector and run until the container is stopped."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()

    # Step 1: database (waits until the db container is ready), create tables
    store = MeasurementStore(settings.database_url, settings.shunt_resistance_ohm)
    ensure_schema(store.conn)
    collector = Collector(settings, store)
    client = build_client(settings, collector)

    # `docker compose stop` sends the signal SIGTERM -> disconnect cleanly.
    def stop(signum, frame):
        log.info("shutting down (%s)", signal.Signals(signum).name)
        client.disconnect()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    log.info("connecting to MQTT broker %s:%s (tls=%s)", settings.mqtt_host, settings.mqtt_port, settings.mqtt_tls)
    # Steps 2-4: connect, subscribe (in on_connect), then wait for messages forever.
    # keepalive=60: send a small "still here" signal every 60 s so the broker
    # notices a dead connection.
    client.connect_async(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    client.loop_forever(retry_first_connection=True)
    # Only reached after stop() above:
    store.close()
    log.info("stopped: %s", collector.stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
