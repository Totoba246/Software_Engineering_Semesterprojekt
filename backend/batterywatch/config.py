"""All settings of the backend in one place.

WHAT THIS FILE DOES
    Reads the settings (database address, MQTT broker, battery rules, ...) from
    "environment variables". Those are named values handed to a program when it
    starts. In Docker they come from the .env file via docker-compose.yml
    (see the `environment:` sections there).

WHO USES IT
    The collector, the API and the tools all call ``get_settings()``, so they
    always agree on the same values. Nothing here talks to the network.

HOW TO CHANGE A SETTING
    Don't edit this file - set the variable in .env (on the server) and restart:
    ``docker compose up -d``. The second argument of every ``_env(...)`` call
    below is only the fallback used when the variable is missing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .contract import DEFAULT_TOPICS


def _env(name: str, default: str) -> str:
    """Return environment variable ``name``, or ``default`` if it is missing/empty."""
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def _env_bool(name: str, default: bool) -> bool:
    """Read a yes/no setting: "1", "true", "yes", "on" all mean yes."""
    return _env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    """Read a decimal number setting."""
    return float(_env(name, str(default)))


def _parse_curve(raw: str) -> list[tuple[float, float]]:
    """Turn the text ``"10.5:0,12.7:100"`` into ``[(10.5, 0.0), (12.7, 100.0)]``.

    Each ``volts:percent`` pair is one point of the battery curve
    (10.5 V = 0 %, 12.7 V = 100 %). See ``battery.state_of_charge``.
    """
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
    """All settings. ``frozen=True`` = can't be changed by accident while running."""

    # --- Database -----------------------------------------------------------
    # Where our PostgreSQL database is: postgresql://USER:PASSWORD@HOST:PORT/DATABASE
    # In Docker: host "db" (the container name) and the INTERNAL port 5432.
    # The fallback (localhost:5432) is for running Python directly on a laptop.
    database_url: str = field(
        default_factory=lambda: _env(
            "DATABASE_URL", "postgresql://batterywatch:batterywatch@localhost:5432/batterywatch"
        )
    )

    # --- MQTT (only used by the collector and the test publisher) ------------
    # Address of the broker. Server: mqtt.ti-labs.ai, tests: "mqtt" or localhost.
    mqtt_host: str = field(default_factory=lambda: _env("MQTT_HOST", "localhost"))
    # 1883 = normal MQTT, 8883 = MQTT with encryption (TLS) - the course broker uses 8883.
    mqtt_port: int = field(default_factory=lambda: int(_env("MQTT_PORT", "1883")))
    # Login at the broker (course broker: user tinf25d-llv). Empty = no login.
    mqtt_username: str | None = field(default_factory=lambda: os.environ.get("MQTT_USERNAME") or None)
    mqtt_password: str | None = field(default_factory=lambda: os.environ.get("MQTT_PASSWORD") or None)
    # Encrypt the connection? Must be True for port 8883.
    mqtt_tls: bool = field(default_factory=lambda: _env_bool("MQTT_TLS", False))
    # Optional own certificate authority file; empty = trust the usual public ones.
    mqtt_ca_file: str | None = field(default_factory=lambda: os.environ.get("MQTT_CA_FILE") or None)
    # Which topics to listen to, comma-separated. "+" = any value in that place.
    # Live broker: traffic-nodes/<device_id>/measurements (e.g. traffic-nodes/101/measurements)
    mqtt_topics: list[str] = field(
        default_factory=lambda: [t.strip() for t in _env("MQTT_TOPIC", DEFAULT_TOPICS).split(",") if t.strip()]
    )
    # Our name at the broker; must be unique there (other groups use the same broker).
    mqtt_client_id: str = field(default_factory=lambda: _env("MQTT_CLIENT_ID", "batterywatch-llv-collector"))

    # --- Battery / status rules (explained in docs/Statusregeln.md) ----------
    # The node measures the voltage behind a small resistor ("shunt", 0.002 Ohm):
    #   U_bat = R_shunt * I_bat + U_measured
    shunt_resistance_ohm: float = field(default_factory=lambda: _env_float("SHUNT_RESISTANCE_OHM", 0.002))
    # Battery voltage (in VOLTS) -> charge level (%), straight lines between the points.
    # PLACEHOLDER: must be confirmed for the real battery type (see docs/Statusregeln.md).
    soc_curve: list[tuple[float, float]] = field(
        default_factory=lambda: _parse_curve(_env("BATTERY_SOC_CURVE", "10.5:0,12.7:100"))
    )
    # Below 20 % = "krit" (red), below 50 % = "niedrig" (yellow), else "ok" (green).
    status_critical_below: float = field(default_factory=lambda: _env_float("STATUS_CRITICAL_BELOW", 20))
    status_low_below: float = field(default_factory=lambda: _env_float("STATUS_LOW_BELOW", 50))
    # The traffic light dims at night, so the load (and the voltage under load)
    # changes over the day. The "current" voltage is averaged over this window.
    smoothing_minutes: int = field(default_factory=lambda: int(_env("SMOOTHING_MINUTES", "60")))
    # The shown position is the average of the GPS positions of this many days
    # (counted back from the newest GPS fix). Smooths out GPS jitter.
    position_days: int = field(default_factory=lambda: int(_env("POSITION_DAYS", "3")))
    # Node 101 sends every 15 minutes; no valid measurement for this long (3 missed
    # messages) marks a device as stale (shown in red as "outdated").
    stale_after_minutes: int = field(default_factory=lambda: int(_env("STALE_AFTER_MINUTES", "45")))

    # --- Login (ADR-09) --------------------------------------------------------
    # How long a login stays valid before you have to log in again.
    session_hours: int = field(default_factory=lambda: int(_env("SESSION_HOURS", "168")))  # 7 days
    # Send the login cookie only over HTTPS. Keep false while the site runs on
    # plain http (localhost, http://212.227.31.76:20800); set true behind HTTPS.
    cookie_secure: bool = field(default_factory=lambda: _env_bool("COOKIE_SECURE", False))
    # Brute-force protection: this many wrong passwords for one username ->
    # that username is blocked for LOGIN_LOCK_MINUTES.
    login_max_failures: int = field(default_factory=lambda: int(_env("LOGIN_MAX_FAILURES", "5")))
    login_lock_minutes: int = field(default_factory=lambda: int(_env("LOGIN_LOCK_MINUTES", "5")))

    # --- API ----------------------------------------------------------------
    # Which other web addresses may call the API from a browser ("*" = all).
    # Only matters during development, when the page runs on a different port.
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in _env("CORS_ORIGINS", "*").split(",") if o.strip()]
    )


def get_settings() -> Settings:
    """Read all settings now (from the current environment variables)."""
    return Settings()
