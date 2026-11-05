"""SQL used by the REST API (read-only)."""

# Latest state of every device:
#  - last:  newest measurement (last_seen, current)
#  - win:   average over the smoothing window before the newest measurement.
#           Single readings scatter by +-0.15 V and the load changes between day and
#           night (the traffic light dims at night), so a single value is too noisy.
#  - pos:   newest measurement that has a GPS fix
DEVICE_STATE = """
SELECT d.device_id, d.tenant, d.device_type, d.name, d.category, d.location,
       last.measured_at              AS last_seen,
       last.current_ma               AS last_current_ma,
       last.battery_voltage_mv       AS last_battery_voltage_mv,
       win.avg_battery_voltage_mv,
       win.avg_current_ma,
       pos.latitude, pos.longitude, pos.altitude_m, pos.satellites
FROM devices d
LEFT JOIN LATERAL (
    SELECT measured_at, current_ma, battery_voltage_mv
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
    SELECT latitude, longitude, altitude_m, satellites
    FROM measurements m
    WHERE m.device_id = d.device_id AND m.latitude IS NOT NULL
    ORDER BY measured_at DESC
    LIMIT 1
) pos ON true
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
