"""Collection service (ADR-10): MQTT broker -> validation -> PostgreSQL.

Run with:  python -m batterywatch.collector
"""

from __future__ import annotations

import logging
import signal
import ssl
import sys
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from ..config import Settings, get_settings
from ..contract import ContractError, parse_message
from ..db import MeasurementStore, ensure_schema

log = logging.getLogger("batterywatch.collector")


class Collector:
    def __init__(self, settings: Settings, store: MeasurementStore):
        self.settings = settings
        self.store = store
        self.stats = {"stored": 0, "duplicate": 0, "rejected": 0}

    def handle_message(self, topic: str, payload: bytes) -> str:
        """Validate and store one message. Returns 'stored', 'duplicate' or 'rejected'."""
        try:
            measurement = parse_message(topic, payload, received_at=datetime.now(timezone.utc))
        except ContractError as exc:
            # ADR-10: invalid messages are discarded and logged, never stored.
            log.warning("rejected message on %s: %s | payload=%r", topic, exc, payload[:300])
            result = "rejected"
        else:
            result = "stored" if self.store.save(measurement) else "duplicate"
            log.debug("%s %s @ %s", result, measurement.device_id, measurement.measured_at.isoformat())
        self.stats[result] += 1
        total = sum(self.stats.values())
        if total % 100 == 0:
            log.info("processed %d messages: %s", total, self.stats)
        return result

    # --- paho callbacks ----------------------------------------------------
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code.is_failure:
            log.error("MQTT connect failed: %s", reason_code)
            return
        # Subscribing here means we re-subscribe automatically after reconnects.
        client.subscribe(self.settings.mqtt_topic, qos=1)
        log.info(
            "connected to %s:%s, subscribed to %r",
            self.settings.mqtt_host,
            self.settings.mqtt_port,
            self.settings.mqtt_topic,
        )

    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        log.warning("MQTT disconnected (%s), paho will reconnect", reason_code)

    def on_message(self, client, userdata, msg):
        try:
            self.handle_message(msg.topic, msg.payload)
        except Exception:  # never let one bad message kill the service
            log.exception("failed to process message on %s", msg.topic)


def build_client(settings: Settings, collector: Collector) -> mqtt.Client:
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=settings.mqtt_client_id,
        # Persistent session: the broker keeps QoS 1 messages while we are offline.
        clean_session=False,
    )
    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
    if settings.mqtt_tls:
        client.tls_set(ca_certs=settings.mqtt_ca_file, cert_reqs=ssl.CERT_REQUIRED)
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.on_connect = collector.on_connect
    client.on_disconnect = collector.on_disconnect
    client.on_message = collector.on_message
    return client


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()

    store = MeasurementStore(settings.database_url, settings.shunt_resistance_ohm)
    ensure_schema(store.conn)
    collector = Collector(settings, store)
    client = build_client(settings, collector)

    def stop(signum, frame):
        log.info("shutting down (%s)", signal.Signals(signum).name)
        client.disconnect()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    log.info("connecting to MQTT broker %s:%s (tls=%s)", settings.mqtt_host, settings.mqtt_port, settings.mqtt_tls)
    client.connect_async(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    client.loop_forever(retry_first_connection=True)
    store.close()
    log.info("stopped: %s", collector.stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
