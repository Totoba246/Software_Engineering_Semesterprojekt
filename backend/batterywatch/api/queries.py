"""The SQL questions the API asks the database.

Kept in one file so you can read and test them separately, e.g. by pasting
them into psql / DBeaver (replace %(name)s with a value first).

Quick SQL glossary for these queries:
    LEFT JOIN LATERAL (...) x ON true  -> "for every device, run this sub-query"
    ORDER BY measured_at DESC LIMIT 1  -> "only the newest row"
    avg(), min(), max(), count()       -> average / smallest / biggest / number of rows
    %(name)s                           -> placeholder, filled in safely by psycopg
"""

# Latest state of every device:
#  - last:  newest measurement (last_seen, current)
#  - win:   average over the smoothing window before the newest measurement.
#           Single readings scatter by +-0.15 V and the load changes between day and
#           night (the traffic light dims at night), so a single value is too noisy.
#  - pos:   AVERAGE position of the GPS fixes of the last POSITION_DAYS days
#           (counted back from the newest fix, so it also works for old data)
#  - msg:   newest received MQTT message, valid or not (shows rejected values)
#  - tech:  the assigned service technician (master data)
# {where} is filled in by the API, e.g. "only devices of technician 7".
DEVICE_STATE = """
SELECT d.device_id, d.tenant, d.device_type, d.name, d.category, d.location,
       d.technician_id, tech.display_name AS technician_name,
       last.measured_at              AS last_seen,
       last.current_ma               AS last_current_ma,
       last.battery_voltage_mv       AS last_battery_voltage_mv,
       last.temperature_c            AS temperature_c,
       msg.received_at               AS last_message_at,
       msg.accepted                  AS last_message_accepted,
       msg.error                     AS last_message_error,
       win.avg_battery_voltage_mv,
       win.avg_current_ma,
       pos.latitude, pos.longitude, pos.altitude_m, pos.satellites, pos.fixes
FROM devices d
LEFT JOIN users tech ON tech.id = d.technician_id
LEFT JOIN LATERAL (
    SELECT measured_at, current_ma, battery_voltage_mv, temperature_c
    FROM measurements m
    WHERE m.device_id = d.device_id
    ORDER BY measured_at DESC
    LIMIT 1
) last ON true
LEFT JOIN LATERAL (
    SELECT avg(battery_voltage_mv) AS avg_battery_voltage_mv, avg(current_ma) AS avg_current_ma
    FROM measurements m
    WHERE m.device_id = d.device_id
      AND m.measured_at > last.measured_at - make_interval(mins => %(window_minutes)s)
      AND m.measured_at <= last.measured_at
) win ON true
LEFT JOIN LATERAL (
    SELECT avg(m.latitude) AS latitude, avg(m.longitude) AS longitude, avg(m.altitude_m) AS altitude_m,
           round(avg(m.satellites))::int AS satellites, count(*) AS fixes
    FROM measurements m
    WHERE m.device_id = d.device_id AND m.latitude IS NOT NULL
      AND m.measured_at >= (SELECT max(g.measured_at) FROM measurements g
                            WHERE g.device_id = d.device_id AND g.latitude IS NOT NULL)
                           - make_interval(days => %(position_days)s)
) pos ON true
LEFT JOIN LATERAL (
    SELECT received_at, accepted, error
    FROM raw_messages r
    WHERE r.device_id = d.device_id
    ORDER BY received_at DESC
    LIMIT 1
) msg ON true
{where}
ORDER BY d.device_id
"""

# Additional figures for the detail page.
#  - trend: linear regression of the battery voltage over the last 72 h, in V/day.
#           72 h = three full day/night cycles, so the dimming plateaus average out.
DEVICE_STATS = """
SELECT count(*)                                         AS measurement_count,
       min(measured_at)                                 AS first_seen,
       (SELECT avg(current_ma) FROM measurements m2
         WHERE m2.device_id = %(device_id)s
           AND m2.measured_at > %(last_seen)s - interval '24 hours') AS avg_current_ma_24h,
       (SELECT regr_slope(battery_voltage_mv, extract(epoch FROM measured_at)) * 86400 / 1000
          FROM measurements m3
         WHERE m3.device_id = %(device_id)s
           AND m3.measured_at > %(last_seen)s - interval '72 hours') AS trend_v_per_day
FROM measurements m
WHERE m.device_id = %(device_id)s
"""

HISTORY = """
SELECT date_bin(make_interval(secs => %(bucket_seconds)s), measured_at, TIMESTAMPTZ '2000-01-01') AS t,
       avg(battery_voltage_mv) AS avg_mv,
       min(battery_voltage_mv) AS min_mv,
       max(battery_voltage_mv) AS max_mv,
       avg(current_ma)         AS avg_ma,
       count(*)                AS n
FROM measurements
WHERE device_id = %(device_id)s
  AND measured_at >  %(start)s
  AND measured_at <= %(end)s
GROUP BY 1
ORDER BY 1
"""

LAST_SEEN = "SELECT max(measured_at) AS last_seen FROM measurements WHERE device_id = %(device_id)s"

MESSAGES = """
SELECT received_at, topic, accepted, error, payload
FROM raw_messages
WHERE device_id = %(device_id)s
ORDER BY received_at DESC
LIMIT %(limit)s
"""

# --- Login -------------------------------------------------------------------
# The logged-in user behind a session token (only if not expired and not locked).
SESSION_USER = """
SELECT u.id, u.username, u.display_name, u.email, u.role, u.must_change_password
FROM sessions s
JOIN users u ON u.id = s.user_id
WHERE s.token_hash = %(token_hash)s AND s.expires_at > now() AND u.active
"""

# --- User management -----------------------------------------------------------
USERS = """
SELECT u.id, u.username, u.display_name, u.email, u.role, u.active, u.must_change_password,
       u.created_at, u.last_login_at,
       (SELECT count(*) FROM devices d WHERE d.technician_id = u.id) AS device_count
FROM users u
{where}
ORDER BY u.display_name
"""
