import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { BatteryIcon } from '../components/Battery.jsx'
import DeviceMap from '../components/DeviceMap.jsx'
import HistoryChart, { METRICS, NIGHT_FROM, NIGHT_TO } from '../components/HistoryChart.jsx'
import { ago, dateTime, num, STATUS_LABEL } from '../format.js'
import { usePolling } from '../usePolling.js'

const RANGES = [
  { hours: 24, label: '24 Std.' },
  { hours: 24 * 7, label: '7 Tage' },
  { hours: 24 * 30, label: '30 Tage' },
  { hours: 'all', label: 'Gesamt' },
]

// whole history of the device (API maximum: one year)
function allHours(device) {
  if (!device.first_seen || !device.last_seen) return 24
  const h = Math.ceil((new Date(device.last_seen) - new Date(device.first_seen)) / 3600e3) + 1
  return Math.min(Math.max(h, 24), 24 * 365)
}

function statusText(d, rules) {
  const crit = rules?.critical_below_percent ?? 20
  const low = rules?.low_below_percent ?? 50
  switch (d.status) {
    case 'krit': return `Akku unter ${crit} %, Wechsel planen`
    case 'niedrig': return `Akku zwischen ${crit} und ${low - 1} %`
    case 'ok': return `Akku ab ${low} %`
    default: return 'Noch keine Messwerte'
  }
}

function HistoryCard({ device, rules }) {
  const [range, setRange] = useState(24 * 7)
  const [metric, setMetric] = useState('soc')
  const hours = range === 'all' ? allHours(device) : range
  const { data, error } = usePolling(() => api.history(device.device_id, hours), [device.device_id, hours])

  const pts = data?.points ?? []
  const first = pts[0]
  const last = pts[pts.length - 1]

  return (
    <section className="card span2" aria-label="Verlauf">
      <div className="card-head">
        <h2>Verlauf</h2>
        <div className="card-tools">
          <div className="seg small" role="group" aria-label="Messgröße">
            {Object.entries(METRICS).map(([k, m]) => (
              <button key={k} type="button" aria-pressed={metric === k} onClick={() => setMetric(k)}>{m.label}</button>
            ))}
          </div>
          <div className="seg small" role="group" aria-label="Zeitraum">
            {RANGES.map((r) => (
              <button key={r.hours} type="button" aria-pressed={range === r.hours} onClick={() => setRange(r.hours)}>{r.label}</button>
            ))}
          </div>
        </div>
      </div>
      {error && <p className="hint warn">Verlauf konnte nicht geladen werden: {error.message}</p>}
      {data && pts.length === 0 && <p className="hint">Keine Messwerte in diesem Zeitraum.</p>}
      {data && pts.length > 0 && <HistoryChart history={data} metric={metric} hours={hours} rules={rules} />}
      <div className="chart-foot">
        {first && last && (
          <span>
            Zeitraum: <b>{dateTime(first.t)}</b> bis <b>{dateTime(last.t)}</b>
          </span>
        )}
        {first && last && metric !== 'current' && (
          <span>
            Veränderung: <b>{num(last.battery_voltage_v - first.battery_voltage_v, 2)} V</b>
          </span>
        )}
        <span>
          <i className="night-key" />Nacht ({NIGHT_FROM}–{NIGHT_TO} Uhr): Ampel gedimmt, weniger Strom → Plateaus in der Spannung
        </span>
        {data && <span>Mittelwert je {data.bucket_seconds / 60} Min., Fläche = Min/Max</span>}
      </div>
    </section>
  )
}

export default function DeviceDetail({ rules }) {
  const { id } = useParams()
  const { data: d, error, loading } = usePolling(() => api.device(id), [id])

  if (error?.status === 404) {
    return (
      <div className="scroll"><div className="detail">
        <Link className="back" to="/">← Zur Übersicht</Link>
        <div className="d-head"><h1>Gerät nicht gefunden</h1><p>Es gibt kein Gerät mit der ID „{id}“.</p></div>
      </div></div>
    )
  }
  if (!d) {
    return (
      <div className="scroll"><div className="detail">
        <Link className="back" to="/">← Zur Übersicht</Link>
        <p className={error ? 'hint warn' : 'hint'}>{error ? `Fehler: ${error.message}` : loading && 'Lade …'}</p>
      </div></div>
    )
  }

  return (
    <div className="scroll">
      <div className="detail">
        <Link className="back" to="/">← Zur Übersicht</Link>
        <div className="d-head">
          <h1>{d.name}</h1>
          <p>{[d.name !== d.device_id && d.device_id, d.tenant, d.device_type, d.location, d.category].filter(Boolean).join(' · ')}</p>
        </div>
        {error && <p className="hint warn">Aktualisierung fehlgeschlagen: {error.message}</p>}
        <div className="d-grid">
          <section className={`card s-${d.status}`} aria-label="Akkustand">
            <div className="bigbatt">
              <span className="bignum">{d.soc_percent != null ? Math.round(d.soc_percent) : '–'}<small>%</small></span>
              <BatteryIcon device={d} />
            </div>
            <p className="status"><i className="dot" />{STATUS_LABEL[d.status]}</p>
            <p>{statusText(d, rules)}</p>
            <p className="hint" style={{ marginTop: 14 }}>
              Akkuspannung {num(d.battery_voltage_v, 2)} V (Mittel der letzten {rules?.smoothing_minutes ?? 60} Min.
              vor der letzten Meldung, inkl. Shunt-Korrektur U<sub>bat</sub> = {num(rules?.shunt_resistance_ohm ?? 0.002, 3)} Ω · I + U<sub>mess</sub>)
            </p>
          </section>

          <section className="card" aria-label="Gerätedaten">
            <dl className="facts">
              <dt>Letzte Meldung</dt>
              <dd className={d.stale ? 'stale' : ''}>{ago(d.minutes_since_last_seen)}<br /><small>{dateTime(d.last_seen)}</small></dd>
              <dt>Letzter Einzelwert</dt>
              <dd>{num(d.last_battery_voltage_v, 3)} V · {num(d.current_a, 3)} A</dd>
              <dt>Ø Strom 24 Std.</dt>
              <dd>{num(d.avg_current_a_24h, 3)} A</dd>
              <dt>Spannungstrend</dt>
              <dd>{d.voltage_trend_v_per_day != null ? `${num(d.voltage_trend_v_per_day, 3)} V pro Tag (72 Std.)` : '–'}</dd>
              <dt>Position</dt>
              <dd>
                {d.position ? `${num(d.position.latitude, 5)}, ${num(d.position.longitude, 5)}` : 'kein GPS'}
                {d.position?.altitude_m != null && ` · ${num(d.position.altitude_m, 0)} m`}
                {d.position?.satellites != null && ` · ${d.position.satellites} Sat.`}
              </dd>
              <dt>Messwerte</dt>
              <dd>{d.measurement_count.toLocaleString('de-DE')} seit {dateTime(d.first_seen)}</dd>
            </dl>
          </section>

          <HistoryCard device={d} rules={rules} />

          <section className="card span2" aria-label="Standort">
            <h2>Standort</h2>
            {d.position ? (
              <div className="mini"><DeviceMap devices={[d]} selectedId={d.device_id} /></div>
            ) : (
              <p className="hint">Für dieses Gerät liegt noch keine GPS-Position vor.</p>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
