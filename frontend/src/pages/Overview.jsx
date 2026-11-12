/*
 * PAGE "Übersicht" / "Meine Geräte" (address /): device list left, map right.
 *
 * The device list comes from App.jsx (GET /api/devices). The SERVER already
 * limits it by role: Servicetechniker only get their assigned devices.
 * Here in the browser: search, filters (F05: status, category, place,
 * technician), sorting. Clicking a device opens /geraete/<id>.
 */

import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { isManagement } from '../api.js'
import { BatteryLevel, Legend } from '../components/Battery.jsx'
import DeviceMap from '../components/DeviceMap.jsx'
import { ago, STATUS_LABEL, STATUS_ORDER } from '../format.js'

const STATUS_FILTERS = ['alle', 'krit', 'niedrig', 'ok']
const UNASSIGNED = '__none__'

const SORTS = {
  urgency: {
    label: 'Dringlichkeit',
    fn: (a, b) =>
      STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || (a.soc_percent ?? 999) - (b.soc_percent ?? 999),
  },
  soc: { label: 'Akkustand', fn: (a, b) => (a.soc_percent ?? 999) - (b.soc_percent ?? 999) },
  name: { label: 'Name', fn: (a, b) => a.name.localeCompare(b.name, 'de') },
  location: { label: 'Ort', fn: (a, b) => (a.location ?? '~').localeCompare(b.location ?? '~', 'de') },
  seen: { label: 'Letzte Meldung', fn: (a, b) => (a.minutes_since_last_seen ?? 1e12) - (b.minutes_since_last_seen ?? 1e12) },
}

const distinct = (list) => [...new Set(list.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'de'))

function EmptyList({ me }) {
  if (me.role === 'techniker') {
    return <div className="empty"><p><strong>Ihnen sind noch keine Geräte zugeordnet.</strong></p>
      <p>Die Zuordnung machen Firmenchef oder Mitarbeiter in der Detailansicht eines Geräts.</p></div>
  }
  return (
    <div className="empty">
      <p><strong>Noch keine Geräte.</strong></p>
      <p>Geräte erscheinen automatisch mit ihrer ersten MQTT-Nachricht – oder legen Sie eines an:
        <Link to="/geraete/neu"> Gerät hinzufügen</Link>.</p>
      <p>Zum Testen: <code>python start.py mode test</code> (erfundene Nodes).</p>
    </div>
  )
}

export default function Overview({ devices, rules, me }) {
  const [params] = useSearchParams()
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState(STATUS_FILTERS.includes(params.get('status')) ? params.get('status') : 'alle')
  const [category, setCategory] = useState(null)
  const [location, setLocation] = useState('')
  const [technician, setTechnician] = useState('')
  const [staleOnly, setStaleOnly] = useState(false)
  const [sort, setSort] = useState('urgency')
  const [hoverId, setHoverId] = useState(null)
  const manager = isManagement(me)

  const all = devices ?? []
  const categories = useMemo(() => distinct(all.map((d) => d.category)), [all])
  const locations = useMemo(() => distinct(all.map((d) => d.location)), [all])
  const technicians = useMemo(() => distinct(all.map((d) => d.technician?.display_name)), [all])

  // Everything except the status filter (so the status buttons can show counts)
  const base = useMemo(() => {
    const q = query.trim().toLowerCase()
    return all.filter(
      (d) =>
        (!category || d.category === category) &&
        (!location || d.location === location) &&
        (!technician || (technician === UNASSIGNED ? !d.technician : d.technician?.display_name === technician)) &&
        (!staleOnly || d.stale) &&
        (!q || [d.name, d.device_id, d.tenant, d.location, d.category, d.technician?.display_name]
          .some((v) => v?.toLowerCase().includes(q))),
    )
  }, [all, query, category, location, technician, staleOnly])

  const counts = useMemo(() => {
    const c = { alle: base.length, krit: 0, niedrig: 0, ok: 0 }
    base.forEach((d) => { if (d.status in c) c[d.status]++ })
    return c
  }, [base])

  const shown = useMemo(
    () => base.filter((d) => status === 'alle' || d.status === status).sort(SORTS[sort].fn),
    [base, status, sort],
  )

  const filtered = query || status !== 'alle' || category || location || technician || staleOnly
  const reset = () => {
    setQuery(''); setStatus('alle'); setCategory(null); setLocation(''); setTechnician(''); setStaleOnly(false)
  }

  return (
    <section className="overview" aria-label="Geräteübersicht">
      <aside className="side">
        <div className="filters">
          {manager && <Link className="btn add-btn" to="/geraete/neu">+ Gerät hinzufügen</Link>}
          <label className="field">
            <span>Suche</span>
            <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Name, Geräte-ID, Ort …" />
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
          {categories.length > 0 && (
            <fieldset>
              <legend>Kategorie</legend>
              <div className="chips">
                {categories.map((c) => (
                  <button key={c} type="button" className="chip" aria-pressed={category === c} onClick={() => setCategory(category === c ? null : c)}>
                    {c}
                  </button>
                ))}
              </div>
            </fieldset>
          )}
          <div className="two">
            {locations.length > 0 && (
              <label className="field">
                <span>Ort</span>
                <select value={location} onChange={(e) => setLocation(e.target.value)}>
                  <option value="">Alle Orte</option>
                  {locations.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </label>
            )}
            {manager && (
              <label className="field">
                <span>Servicetechniker</span>
                <select value={technician} onChange={(e) => setTechnician(e.target.value)}>
                  <option value="">Alle</option>
                  <option value={UNASSIGNED}>– nicht zugeordnet –</option>
                  {technicians.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
            )}
          </div>
          <div className="chips">
            <button type="button" className="chip" aria-pressed={staleOnly} onClick={() => setStaleOnly(!staleOnly)}>
              Ohne aktuelle Meldung (&gt; {rules?.stale_after_minutes ?? 45} Min.)
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
          <EmptyList me={me} />
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
                        [d.name !== d.device_id && d.device_id, d.location, d.category,
                          d.battery_voltage_v != null && `${d.battery_voltage_v.toFixed(2).replace('.', ',')} V`]
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
