-- BatteryWatch database schema (PostgreSQL >= 14).
-- Idempotent: executed by the API and the collector on startup. Changes to
-- existing tables are appended as ALTER ... IF NOT EXISTS so old databases upgrade.

-- One row per device (TrafficNode). Created automatically by the collector
-- on the first message; name/category/location are master data (F07).
CREATE TABLE IF NOT EXISTS devices (
    device_id    TEXT PRIMARY KEY,
    tenant       TEXT,             -- operator; unknown for traffic-nodes/<id>/measurements
    device_type  TEXT NOT NULL,
    name         TEXT,
    category     TEXT,
    location     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per MQTT message (or imported row).
CREATE TABLE IF NOT EXISTS measurements (
    id                  BIGSERIAL PRIMARY KEY,
    device_id           TEXT NOT NULL REFERENCES devices (device_id) ON DELETE CASCADE,
    measured_at         TIMESTAMPTZ NOT NULL,              -- time from the payload (or receive time)
    received_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    current_ma          DOUBLE PRECISION NOT NULL,         -- I_measured
    voltage_mv          DOUBLE PRECISION NOT NULL,         -- U_measured (behind the shunt)
    battery_voltage_mv  DOUBLE PRECISION NOT NULL,         -- U_bat = R_shunt * I + U_measured
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    altitude_m          DOUBLE PRECISION,
    satellites          INTEGER,
    source              TEXT NOT NULL DEFAULT 'mqtt',      -- 'mqtt' or 'import'
    -- Duplicate deliveries (MQTT QoS 1, repeated imports) are ignored.
    -- The unique index also serves all "latest values / history of a device" queries.
    CONSTRAINT measurements_device_time_uq UNIQUE (device_id, measured_at)
);

-- Every received MQTT message, valid or not: lets us see that a node is alive
-- and why its messages are rejected (e.g. implausible voltage).
CREATE TABLE IF NOT EXISTS raw_messages (
    id           BIGSERIAL PRIMARY KEY,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    topic        TEXT NOT NULL,
    device_id    TEXT,                                     -- NULL if the topic was invalid
    payload      TEXT NOT NULL,
    accepted     BOOLEAN NOT NULL,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS raw_messages_device_time_idx ON raw_messages (device_id, received_at DESC);

-- v2: live broker layout without tenant, temperature from the node
ALTER TABLE devices ALTER COLUMN tenant DROP NOT NULL;
ALTER TABLE measurements ADD COLUMN IF NOT EXISTS temperature_c DOUBLE PRECISION;
