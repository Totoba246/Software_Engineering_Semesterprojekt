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

-- =============================================================================
-- v3: login, roles and device master data (F06, F07, F09)
-- =============================================================================

-- People who can log in. Roles (see README 1.c and the use-case diagram):
--   admin       user accounts + system settings, no device views
--   chef        Firmenchef: all devices, master data, assign technicians
--   mitarbeiter same rights as chef
--   techniker   Servicetechniker: only the devices assigned to them
CREATE TABLE IF NOT EXISTS users (
    id                    SERIAL PRIMARY KEY,
    username              TEXT NOT NULL UNIQUE,      -- login name, stored lower case
    display_name          TEXT NOT NULL,
    email                 TEXT,
    role                  TEXT NOT NULL CHECK (role IN ('admin', 'chef', 'mitarbeiter', 'techniker')),
    password_hash         TEXT NOT NULL,             -- Argon2 hash, never the password itself
    must_change_password  BOOLEAN NOT NULL DEFAULT true,  -- start password set by an admin
    active                BOOLEAN NOT NULL DEFAULT true,  -- false = locked, cannot log in
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at         TIMESTAMPTZ
);

-- One row per logged-in browser. The browser only holds a random token in an
-- HttpOnly cookie; we store its SHA-256 hash, so a database leak reveals no tokens.
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);

-- Device master data: the assigned technician (one per device, F09).
-- The position is NOT master data: it is the average GPS position of the
-- last days (see api/queries.py). Earlier versions had manual coordinates.
ALTER TABLE devices ADD COLUMN IF NOT EXISTS technician_id INTEGER REFERENCES users (id) ON DELETE SET NULL;
ALTER TABLE devices DROP COLUMN IF EXISTS manual_latitude;
ALTER TABLE devices DROP COLUMN IF EXISTS manual_longitude;

-- =============================================================================
-- v4: calendar (F12, F13)
-- =============================================================================

-- Private replacement appointments of the service technicians (F13, issue #12):
-- "I want to replace the battery of device 101 on Tuesday at 08:30".
-- Only the technician who made an appointment can see it (api/appointments.py).
-- The expected failures (F12, issue #11) are not stored: they are calculated
-- from the measurements every time (estimated_critical_at / estimated_empty_at).
CREATE TABLE IF NOT EXISTS appointments (
    id             SERIAL PRIMARY KEY,
    technician_id  INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    device_id      TEXT NOT NULL REFERENCES devices (device_id) ON DELETE CASCADE,
    starts_at      TIMESTAMPTZ NOT NULL,    -- date + time of the planned replacement
    note           TEXT,                    -- e.g. "Ersatzakku aus dem Lager mitnehmen"
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS appointments_technician_time_idx ON appointments (technician_id, starts_at);
