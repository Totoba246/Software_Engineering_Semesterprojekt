"""Central configuration, read from environment variables.

Every service (API, collector, tools) reads its settings from here so that
Docker Compose, CI and local development only differ in their environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


def _parse_curve(raw: str) -> list[tuple[float, float]]:
    """Parse ``"10.5:0,12.7:100"`` into ``[(10.5, 0.0), (12.7, 100.0)]``."""
    points = []
    for pair in raw.split(","):
        volts, percent = pair.split(":")
        points.append((float(volts), float(percent)))
    points.sort()
    if len(points) < 2:
        raise ValueError("BATTERY_SOC_CURVE needs at least two points")
    return points


@dataclass(frozen=True)
class Settings:
    # --- Database -----------------------------------------------------------
    database_url: str = field(
        default_factory=lambda: _env(
            "DATABASE_URL", "postgresql://batterywatch:batterywatch@localhost:5432/batterywatch"
        )
    )

    # --- MQTT ---------------------------------------------------------------
    mqtt_host: str = field(default_factory=lambda: _env("MQTT_HOST", "localhost"))
    mqtt_port: int = field(default_factory=lambda: int(_env("MQTT_PORT", "1883")))
    mqtt_username: str | None = field(default_factory=lambda: os.environ.get("MQTT_USERNAME") or None)
    mqtt_password: str | None = field(default_factory=lambda: os.environ.get("MQTT_PASSWORD") or None)
    mqtt_tls: bool = field(default_factory=lambda: _env_bool("MQTT_TLS", False))
    mqtt_ca_file: str | None = field(default_factory=lambda: os.environ.get("MQTT_CA_FILE") or None)
    # Subscription filter; matches traffic-device/<tenant>/<type>/<device_id>/status
    mqtt_topic: str = field(default_factory=lambda: _env("MQTT_TOPIC", "traffic-device/+/+/+/status"))
    mqtt_client_id: str = field(default_factory=lambda: _env("MQTT_CLIENT_ID", "batterywatch-llv-collector"))

    # --- Battery / status rules --------------------------------------------
    # U_bat = R_shunt * I_bat + U_measured  (TrafficNode measures behind a 2 mOhm shunt)
    shunt_resistance_ohm: float = field(default_factory=lambda: _env_float("SHUNT_RESISTANCE_OHM", 0.002))
    # Battery voltage (V) -> state of charge (%), piecewise linear.
    # PLACEHOLDER: must be confirmed for the real battery type (see docs/Statusregeln.md).
    soc_curve: list[tuple[float, float]] = field(
        default_factory=lambda: _parse_curve(_env("BATTERY_SOC_CURVE", "10.5:0,12.7:100"))
    )
    status_critical_below: float = field(default_factory=lambda: _env_float("STATUS_CRITICAL_BELOW", 20))
    status_low_below: float = field(default_factory=lambda: _env_float("STATUS_LOW_BELOW", 50))
    # The traffic light dims at night, so the load (and the voltage under load)
    # changes over the day. The "current" voltage is averaged over this window.
    smoothing_minutes: int = field(default_factory=lambda: int(_env("SMOOTHING_MINUTES", "60")))
    # Nodes send every ~3 minutes; no message for this long marks a device as stale.
    stale_after_minutes: int = field(default_factory=lambda: int(_env("STALE_AFTER_MINUTES", "30")))

    # --- API ----------------------------------------------------------------
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in _env("CORS_ORIGINS", "*").split(",") if o.strip()]
    )


def get_settings() -> Settings:
    return Settings()
