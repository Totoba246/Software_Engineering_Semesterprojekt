/*
 * PAGE "Übersicht" (address /): list of all devices on the left, map on the right.
 *
 * Gets the device list from App.jsx (which loads it from GET /api/devices).
 * Everything else happens here in the browser: search, filter by status
 * (Kritisch / Niedrig / Gut), sort. Clicking a device opens /geraete/<id>.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BatteryLevel, Legend } from '../components/Battery.jsx'
import DeviceMap from '../components/DeviceMap.jsx'
import { ago, STATUS_LABEL, STATUS_ORDER } from '../format.js'

const STATUS_FILTERS = ['alle', 'krit', 'niedrig', 'ok']

const SORTS = {
  urgency: {
    label: 'Dringlichkeit',
    fn: (a, b) =>
      STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || (a.soc_percent ?? 999) - (b.soc_percent ?? 999),
  },
  soc: { label: 'Akkustand', fn: (a, b) => (a.soc_percent ?? 999) - (b.soc_percent ?? 999) },
  name: { label: 'Name', fn: (a, b) => a.name.localeCompare(b.name, 'de') },
  seen: { label: 'Letzte Meldung', fn: (a, b) => (a.minutes_since_last_seen ?? 1e12) - (b.minutes_since_last_seen ?? 1e12) },
}

function EmptyDatabase() {
  return (
    <div className="empty">
      <p><strong>Noch keine Geräte in der Datenbank.</strong></p>
      <p>Sobald der Collector die erste MQTT-Nachricht speichert, erscheint das Gerät hier.</p>
      <p>Zum Testen z. B. den Testpublisher starten:<br />
        <code>docker compose --profile test up publisher</code></p>
      <p>oder die Beispieldaten importieren:<br />
        <code>python -m batterywatch.tools.import_data csv …</code></p>
    </div>
  )
}

export default function Overview({ devices, rules }) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('alle')
  const [tenant, setTenant] = useState(null)
  const [staleOnly, setStaleOnly] = useState(false)
  const [sort, setSort] = useState('urgency')
  const [hoverId, setHoverId] = useState(null)

  const all = devices ?? []
  const tenants = useMemo(() => [...new Set(all.map((d) => d.tenant).filter(Boolean))].sort(), [all])

  // Everything except the status filter (so the status buttons can show counts)
  const base = useMemo(() => {
    const q = query.trim().toLowerCase()
    return all.filter(
      (d) =>
        (!tenant || d.tenant === tenant) &&
        (!staleOnly || d.stale) &&
        (!q || [d.name, d.device_id, d.tenant, d.location, d.category].some((v) => v?.toLowerCase().includes(q))),
    )
  }, [all, query, tenant, staleOnly])

  const counts = useMemo(() => {
    const c = { alle: base.length, krit: 0, niedrig: 0, ok: 0 }
    base.forEach((d) => { if (d.status in c) c[d.status]++ })
    return c
  }, [base])

  const shown = useMemo(
    () => base.filter((d) => status === 'alle' || d.status === status).sort(SORTS[sort].fn),
    [base, status, sort],
  )

  const filtered = query || status !== 'alle' || tenant || staleOnly
  const reset = () => { setQuery(''); setStatus('alle'); setTenant(null); setStaleOnly(false) }

  return (
    <section className="overview" aria-label="Geräteübersicht">
      <aside className="side">
        <div className="filters">
          <label className="field">
            <span>Suche</span>
            <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Name, Geräte-ID, Betreiber …" />
          </label>
          <fieldset>
            <legend>Akkustand</legend>
            <div className="seg">
              {STATUS_FILTERS.map((s) => (
                <button key={s} type="button" aria-pressed={status === s} onClick={() => setStatus(s)} className={`s-${s}`}>
                  {s !== 'alle' && <i className="dot" />}
                  {s === 'alle' ? 'Alle' : STATUS_LABEL[s]} <span className="n">{counts[s]}</span>
                </button>
              ))}
            </div>
          </fieldset>
          {tenants.length > 1 && (
            <fieldset>
              <legend>Betreiber</legend>
              <div className="chips">
                {tenants.map((t) => (
                  <button key={t} type="button" className="chip" aria-pressed={tenant === t} onClick={() => setTenant(tenant === t ? null : t)}>
                    {t}
                  </button>
                ))}
              </div>
            </fieldset>
          )}
          <div className="chips">
            <button type="button" className="chip" aria-pressed={staleOnly} onClick={() => setStaleOnly(!staleOnly)}>
              Ohne aktuelle Meldung (&gt; {rules?.stale_after_minutes ?? 30} Min.)
            </button>
          </div>
          <label className="field">
            <span>Sortierung</span>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              {Object.entries(SORTS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
            </select>
          </label>
          {filtered && <button type="button" className="reset" onClick={reset}>Filter zurücksetzen</button>}
        </div>
        <div className="list-head">
          <span><strong>{shown.length}</strong> von {all.length} Geräten</span>
          <span>Letzte Meldung</span>
        </div>
        {devices && all.length === 0 ? (
          <EmptyDatabase />
        ) : shown.length === 0 && devices ? (
          <div className="empty">
            <p>Keine Geräte passen zu den Filtern.</p>
            <button type="button" className="reset" onClick={reset}>Filter zurücksetzen</button>
          </div>
        ) : (
          <ul className="list">
            {shown.map((d) => (
              <li key={d.device_id}>
                <Link
                  to={`/geraete/${encodeURIComponent(d.device_id)}`}
                  className={`row${hoverId === d.device_id ? ' hl' : ''}`}
                  onMouseEnter={() => setHoverId(d.device_id)}
                  onMouseLeave={() => setHoverId(null)}
                >
                  <BatteryLevel device={d} />
                  <span className="info">
                    <span className="name">{d.name}</span>
                    <span className="meta">
                      {d.last_message_error ? (
                        <span className="warn">Letzte Nachricht ungültig</span>
                      ) : (
                        [d.name !== d.device_id && d.device_id, d.tenant, d.location, d.battery_voltage_v != null && `${d.battery_voltage_v.toFixed(2).replace('.', ',')} V`]
                          .filter(Boolean)
                          .join(' · ')
                      )}
                    </span>
                  </span>
                  <span className={`seen${d.stale ? ' stale' : ''}`}>
                    {ago(d.minutes_since_last_message ?? d.minutes_since_last_seen)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </aside>
      <div className="ov-map">
        <DeviceMap devices={shown} selectedId={hoverId} onHover={setHoverId} />
        <Legend rules={rules} />
      </div>
    </section>
  )
}
