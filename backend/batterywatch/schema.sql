-- =============================================================================
--  BatteryWatch database tables (PostgreSQL >= 14)
-- =============================================================================
--  This file is run automatically every time the API or the collector starts
--  (db.py -> ensure_schema). "IF NOT EXISTS" makes that safe: existing tables
--  and data are left alone. Changes to existing tables are appended at the
--  bottom as ALTER ... so older databases get upgraded on the next start.
--
--  Three tables:
--    devices       one row per node (e.g. "101")
--    measurements  one row per VALID message: the actual battery data
--    raw_messages  one row per RECEIVED message, valid or not (for diagnosis)
--
--  Look at the data yourself (on the server, or via SSH tunnel, see docs/Server.md):
--    docker compose exec db psql -U batterywatch batterywatch
--    SELECT * FROM devices;
--    SELECT * FROM measurements ORDER BY measured_at DESC LIMIT 10;
--    SELECT received_at, accepted, error FROM raw_messages ORDER BY id DESC LIMIT 10;
-- =============================================================================

-- One row per device (TrafficNode). Created automatically by the collector
-- on the first message; name/category/location are master data (F07).
CREATE TABLE IF NOT EXISTS devices (
    device_id    TEXT PRIMARY KEY, -- e.g. "101" (from the MQTT topic); unique
    tenant       TEXT,             -- operator; unknown for traffic-nodes/<id>/measurements
    device_type  TEXT NOT NULL,    -- always "trafficnode" for now
    name         TEXT,             -- display name (not filled yet; the page shows device_id)
    category     TEXT,             -- e.g. "Baustellenampel" (not filled yet)
    location     TEXT,             -- e.g. "Rottweil, Hauptstraße" (not filled yet)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()  -- when we first heard from it
);

-- One row per valid MQTT message (or imported row). All values exactly as sent
-- (milliVOLT, milliAMPERE) plus the corrected battery voltage.
CREATE TABLE IF NOT EXISTS measurements (
    id                  BIGSERIAL PRIMARY KEY,                -- running number
    device_id           TEXT NOT NULL REFERENCES devices (device_id) ON DELETE CASCADE,
    measured_at         TIMESTAMPTZ NOT NULL,              -- time from the payload (or receive time); UTC
    received_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    current_ma          DOUBLE PRECISION NOT NULL,         -- I_measured in mA
    voltage_mv          DOUBLE PRECISION NOT NULL,         -- U_measured in mV (behind the shunt)
    battery_voltage_mv  DOUBLE PRECISION NOT NULL,         -- U_bat = R_shunt * I + U_measured, in mV
    latitude            DOUBLE PRECISION,                  -- GPS, NULL without satellite fix
    longitude           DOUBLE PRECISION,
    altitude_m          DOUBLE PRECISION,
    satellites          INTEGER,
    source              TEXT NOT NULL DEFAULT 'mqtt',      -- 'mqtt' (live) or 'import'
    -- Duplicate deliveries (MQTT QoS 1, repeated imports) are ignored.
    -- The unique index also serves all "latest values / history of a device" queries.
    CONSTRAINT measurements_device_time_uq UNIQUE (device_id, measured_at)
);

-- Every received MQTT message, valid or not: lets us see that a node is alive
-- and why its messages are rejected (e.g. implausible voltage).
CREATE TABLE IF NOT EXISTS raw_messages (
    id           BIGSERIAL PRIMARY KEY,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    topic        TEXT NOT NULL,                            -- e.g. traffic-nodes/101/measurements
    device_id    TEXT,                                     -- NULL if the topic was invalid
    payload      TEXT NOT NULL,                            -- the message text exactly as received
    accepted     BOOLEAN NOT NULL,                         -- true = became a measurement
    error        TEXT                                      -- German reason if rejected
);
-- An index = a sorted lookup list, so "newest messages of device X" is fast.
CREATE INDEX IF NOT EXISTS raw_messages_device_time_idx ON raw_messages (device_id, received_at DESC);

-- v2: live broker layout without tenant, temperature from the node
ALTER TABLE devices ALTER COLUMN tenant DROP NOT NULL;
ALTER TABLE measurements ADD COLUMN IF NOT EXISTS temperature_c DOUBLE PRECISION;  -- degrees Celsius
