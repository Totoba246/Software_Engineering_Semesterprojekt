/*
 * THE CHART on the detail page (library "Recharts").
 * Draws the averaged values from GET /api/devices/<id>/history:
 *   line = average per time slot, light band = min..max in that slot.
 * Night hours (21-6 Uhr, German time) are shaded: the traffic light dims at
 * night, draws less current, and the voltage forms "plateaus" - that's normal.
 */

import { useMemo } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { socFromVoltage } from '../battery.js'
import { num } from '../format.js'

// The traffic light dims at night (≈ 21–6 Uhr): less current, so the voltage
// under load forms plateaus. These hours are shaded in the chart.
export const NIGHT_FROM = 21
export const NIGHT_TO = 6

export const METRICS = {
  soc: { label: 'Akkustand', unit: '%', digits: 0 },
  voltage: { label: 'Spannung', unit: 'V', digits: 2 },
  current: { label: 'Strom', unit: 'A', digits: 2 },
}

// Night hours are evaluated in German time, independent of the viewer's time zone.
const berlinHour = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Berlin', hour: 'numeric', hourCycle: 'h23' })
const isNight = (t) => {
  const h = Number(berlinHour.formatToParts(new Date(t)).find((p) => p.type === 'hour').value)
  return h >= NIGHT_FROM || h < NIGHT_TO
}

function nightIntervals(start, end) {
  const HOUR = 3600e3
  const out = []
  let open = null
  for (let t = Math.floor(start / HOUR) * HOUR; t < end; t += HOUR) {
    if (isNight(t)) {
      if (open == null) open = Math.max(t, start)
    } else if (open != null) {
      out.push([open, t])
      open = null
    }
  }
  if (open != null) out.push([open, end])
  return out
}

function toRows(history, metric, curve) {
  const rows = []
  const gap = history.bucket_seconds * 1000 * 3
  let prev = null
  for (const p of history.points) {
    const t = new Date(p.t).getTime()
    if (prev != null && t - prev > gap) rows.push({ t: prev + 1, value: null, band: null }) // break the line
    prev = t
    let value, band
    if (metric === 'soc') {
      value = p.soc_percent
      band = [socFromVoltage(p.battery_voltage_min_v, curve), socFromVoltage(p.battery_voltage_max_v, curve)]
    } else if (metric === 'voltage') {
      value = p.battery_voltage_v
      band = [p.battery_voltage_min_v, p.battery_voltage_max_v]
    } else {
      value = p.current_a
      band = null
    }
    rows.push({ t, value, band, samples: p.samples })
  }
  return rows
}

// Ticks on full hours (short ranges) or at midnight (long ranges), max ~10 per axis.
function makeTicks(start, end, hours) {
  const ticks = []
  const d = new Date(start)
  if (hours <= 48) {
    const step = hours <= 24 ? 3 : 6
    d.setMinutes(0, 0, 0)
    d.setHours(Math.ceil(d.getHours() / step) * step)
    for (; d.getTime() <= end; d.setHours(d.getHours() + step)) ticks.push(d.getTime())
  } else {
    const step = Math.max(1, Math.ceil(hours / 24 / 10))
    d.setHours(24, 0, 0, 0)
    for (; d.getTime() <= end; d.setDate(d.getDate() + step)) ticks.push(d.getTime())
  }
  return ticks
}

function tickFormatter(hours) {
  const f =
    hours <= 48
      ? new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit' })
      : new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit' })
  return (t) => f.format(new Date(t))
}

const tipTime = new Intl.DateTimeFormat('de-DE', {
  weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
})

function ChartTip({ active, payload, metric }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  if (row.value == null) return null
  const m = METRICS[metric]
  return (
    <div className="tip">
      {tipTime.format(new Date(row.t))}
      <br />
      {m.label}: {num(row.value, m.digits)} {m.unit}
      {row.band && row.band[0] != null && (
        <>
          <br />
          Spanne: {num(row.band[0], m.digits)} – {num(row.band[1], m.digits)} {m.unit}
        </>
      )}
      <br />
      <span style={{ opacity: 0.7 }}>{row.samples} Messwerte</span>
    </div>
  )
}

export default function HistoryChart({ history, metric, hours, rules }) {
  const start = new Date(history.start).getTime()
  const end = new Date(history.end).getTime()
  const rows = useMemo(() => toRows(history, metric, rules?.soc_curve), [history, metric, rules])
  const nights = useMemo(() => nightIntervals(start, end), [start, end])
  const ticks = useMemo(() => makeTicks(start, end, hours), [start, end, hours])
  const m = METRICS[metric]

  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          {nights.map(([a, b]) => (
            <ReferenceArea key={a} x1={a} x2={b} fill="var(--night)" fillOpacity={0.08} stroke="none" ifOverflow="hidden" />
          ))}
          <CartesianGrid stroke="var(--line)" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={[start, end]}
            ticks={ticks}
            tickFormatter={tickFormatter(hours)}
            tick={{ fill: 'var(--muted)', fontSize: 12 }}
            stroke="var(--line)"
            minTickGap={24}
          />
          <YAxis
            domain={metric === 'soc' ? [0, 100] : ['auto', 'auto']}
            tickFormatter={(v) => num(v, { soc: 0, voltage: 1, current: 2 }[metric])}
            tick={{ fill: 'var(--muted)', fontSize: 12 }}
            stroke="var(--line)"
            width={44}
          />
          {metric === 'soc' && rules && (
            <>
              <ReferenceLine y={rules.critical_below_percent} stroke="var(--red)" strokeDasharray="4 4" />
              <ReferenceLine y={rules.low_below_percent} stroke="var(--amber)" strokeDasharray="4 4" />
            </>
          )}
          {metric !== 'current' && (
            <Area
              dataKey="band"
              stroke="none"
              fill="var(--accent)"
              fillOpacity={0.12}
              isAnimationActive={false}
              connectNulls={false}
            />
          )}
          <Line
            dataKey="value"
            stroke="var(--accent)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
          <Tooltip content={<ChartTip metric={metric} />} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
