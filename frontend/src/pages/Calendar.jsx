/*
 * PAGE "Kalender" (address /kalender, optionally /kalender?g=101 to jump to a device)
 *
 *   F12 / issue #11  expected battery failures in a month view.
 *                    Two entries per device, both calculated by the server from the
 *                    voltage trend of the last 72 h (GET /api/devices):
 *                      yellow  "wird kritisch"       estimated_critical_at (< 20 %)
 *                      red     "voraussichtlich leer" estimated_empty_at   (0 %)
 *                    Firmenchef/Mitarbeiter see all devices, Servicetechniker only
 *                    their own (the server filters the device list).
 *   F13 / issue #12  Servicetechniker enter PRIVATE appointments: when they want to
 *                    replace which battery (blue). Only they can see them
 *                    (GET/POST/DELETE /api/appointments, other roles get 403).
 *
 * Layout taken from the GUI draft batterywatch-entwurf.html (section "Kalender"):
 * month grid on the left; on the right the selected day, the appointment form
 * (technicians only) and the devices that are due next.
 */

import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { BatteryLevel } from '../components/Battery.jsx'
import { pct } from '../format.js'
import { usePolling } from '../usePolling.js'

const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
const WEEKDAYS_LONG = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag']
const MONTHS = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
const DAY = 24 * 3600e3

const p2 = (n) => String(n).padStart(2, '0')
// "2026-11-17" in the browser's time zone (the key of a calendar day)
export const dayKey = (date) => {
  const d = new Date(date)
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`
}
const parseKey = (key) => {
  const [y, m, d] = key.split('-').map(Number)
  return new Date(y, m - 1, d)
}
const hhmm = (date) => {
  const d = new Date(date)
  return `${p2(d.getHours())}:${p2(d.getMinutes())}`
}
export const shortDay = (date) => {
  const d = new Date(date)
  return `${WEEKDAYS_LONG[d.getDay()].slice(0, 2)} ${d.getDate()}.${p2(d.getMonth() + 1)}.`
}

// The date the device should be replaced by: when it becomes critical (or empty).
const dueAt = (d) => d.estimated_critical_at ?? d.estimated_empty_at
// Suggested replacement day: one day before it becomes critical, at the earliest today.
export function suggestedDay(d) {
  const due = dueAt(d)
  const today = new Date()
  if (!due) return dayKey(today)
  return dayKey(Math.max(today.getTime(), new Date(due).getTime() - DAY))
}

const EVENT = {
  appt: { cls: 'appt', order: 0 },
  crit: { cls: 's-niedrig', order: 1, label: 'wird kritisch' },
  empty: { cls: 's-krit', order: 2, label: 'voraussichtlich leer' },
}

function buildEvents(devices, appointments) {
  const byDay = {}
  const add = (at, ev) => (byDay[dayKey(at)] ??= []).push({ ...ev, at })
  for (const d of devices) {
    if (d.estimated_critical_at) add(d.estimated_critical_at, { type: 'crit', d })
    if (d.estimated_empty_at) add(d.estimated_empty_at, { type: 'empty', d })
  }
  const byId = Object.fromEntries(devices.map((d) => [d.device_id, d]))
  for (const a of appointments) add(a.starts_at, { type: 'appt', a, d: byId[a.device_id] })
  for (const list of Object.values(byDay)) {
    list.sort((x, y) => EVENT[x.type].order - EVENT[y.type].order || new Date(x.at) - new Date(y.at))
  }
  return byDay
}

function DeviceName({ d, fallback }) {
  return d ? <Link to={`/geraete/${encodeURIComponent(d.device_id)}`}>{d.name}</Link> : <b>{fallback}</b>
}

/* --- month grid ---------------------------------------------------------------------- */
function MonthGrid({ month, sel, events, onSelect }) {
  const first = new Date(month.y, month.m, 1)
  const offset = (first.getDay() + 6) % 7 // Monday = first column
  const days = new Date(month.y, month.m + 1, 0).getDate()
  const cells = Math.ceil((offset + days) / 7) * 7
  const today = dayKey(new Date())
  return (
    <div className="cal-grid">
      {WEEKDAYS.map((w) => <div key={w} className="cal-dow">{w}</div>)}
      {Array.from({ length: cells }, (_, i) => {
        const date = new Date(month.y, month.m, 1 - offset + i)
        const key = dayKey(date)
        const list = events[key] ?? []
        const cls = ['cal-day', date.getMonth() !== month.m && 'out', key === today && 'today', key === sel && 'sel']
          .filter(Boolean).join(' ')
        const label = `${WEEKDAYS_LONG[date.getDay()]}, ${date.getDate()}. ${MONTHS[date.getMonth()]}: ` +
          (list.length ? `${list.length} ${list.length === 1 ? 'Eintrag' : 'Einträge'}` : 'keine Einträge')
        return (
          <button key={key} type="button" className={cls} aria-label={label} aria-pressed={key === sel}
            onClick={() => onSelect(key)}>
            <span className="num">{date.getDate()}</span>
            {list.slice(0, 3).map((e, j) => (
              <span key={j} className={`ev ${EVENT[e.type].cls}`}>
                {e.type === 'appt' ? `${hhmm(e.at)} ${e.d?.name ?? e.a.device_name}` : e.d.name}
              </span>
            ))}
            {list.length > 3 && <span className="ev-more">+{list.length - 3} weitere</span>}
            {list.length > 0 && (
              <span className="dots" aria-hidden="true">
                {list.map((e, j) => <i key={j} className={`dot ${EVENT[e.type].cls}`} />)}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/* --- the selected day ----------------------------------------------------------------------- */
function DayAgenda({ list, tech, onPlan, onDelete }) {
  if (!list.length) {
    return <p className="hint">Keine {tech ? 'Ausfälle oder Termine' : 'voraussichtlichen Ausfälle'} an diesem Tag.</p>
  }
  const now = Date.now()
  return (
    <ul className="agenda">
      {list.map((e, i) => {
        if (e.type === 'appt') {
          return (
            <li key={`a${e.a.id}`} className="ag appt"><i className="dot" />
              <div>
                <b>{hhmm(e.at)} Uhr · Batteriewechsel</b>
                <DeviceName d={e.a.assigned ? e.d : null} fallback={e.a.device_name} />
                {!e.a.assigned && <span className="meta warn">Gerät ist Ihnen nicht mehr zugeordnet</span>}
                {e.a.note && <span className="meta">{e.a.note}</span>}
                <button type="button" className="reset" onClick={() => onDelete(e.a)}>Termin löschen</button>
              </div>
            </li>
          )
        }
        const past = new Date(e.at).getTime() <= now
        const what = e.type === 'crit' ? (past ? 'Bereits kritisch' : 'Wird kritisch') : (past ? 'Bereits leer' : 'Voraussichtlich leer')
        return (
          <li key={`${e.type}${e.d.device_id}${i}`} className={`ag ${EVENT[e.type].cls}`}><i className="dot" />
            <div>
              <DeviceName d={e.d} />
              <span className="meta">
                {what}{!past && ` gegen ${hhmm(e.at)} Uhr`}, aktuell {pct(e.d.soc_percent)}
              </span>
              {tech ? (
                <button type="button" className="reset" onClick={() => onPlan(e.d)}>Wechsel einplanen</button>
              ) : (
                <span className="meta">
                  {e.d.technician ? `Servicetechniker: ${e.d.technician.display_name}` : <span className="warn">Kein Servicetechniker zugeordnet</span>}
                </span>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

/* --- form for an own appointment (Servicetechniker, F13) -------------------------------------- */
function AppointmentForm({ devices, form, setForm, onSaved }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  if (!devices.length) return <p className="hint">Ihnen sind noch keine Geräte zugeordnet.</p>

  // warnings like in the GUI draft: too late or in the past (saving is still allowed)
  const d = devices.find((x) => x.device_id === form.device)
  let hint = { warn: false, text: 'Termine sind privat und nur für Sie sichtbar.' }
  if (form.date && form.date < dayKey(new Date())) hint = { warn: true, text: 'Das Datum liegt in der Vergangenheit.' }
  else if (d?.estimated_empty_at && form.date > dayKey(d.estimated_empty_at)) {
    hint = { warn: true, text: `Achtung: Das Gerät ist voraussichtlich schon am ${shortDay(d.estimated_empty_at)} leer.` }
  } else if (d?.estimated_critical_at && form.date > dayKey(d.estimated_critical_at)) {
    hint = { warn: true, text: `Hinweis: Der Akku ist voraussichtlich ab ${shortDay(d.estimated_critical_at)} kritisch.` }
  }

  async function submit(e) {
    e.preventDefault()
    if (!form.device || !form.date || !form.time) {
      setError('Bitte Gerät, Datum und Uhrzeit angeben.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const starts_at = new Date(`${form.date}T${form.time}`).toISOString() // local time -> UTC
      const saved = await api.createAppointment({ device_id: form.device, starts_at, note: form.note })
      onSaved(saved)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const sorted = [...devices].sort((a, b) => (dueAt(a) ? new Date(dueAt(a)) : Infinity) - (dueAt(b) ? new Date(dueAt(b)) : Infinity))
  return (
    <form className="form" onSubmit={submit} noValidate>
      <label className="field"><span>Gerät</span>
        <select value={form.device} onChange={set('device')} required>
          <option value="">Gerät wählen</option>
          {sorted.map((x) => <option key={x.device_id} value={x.device_id}>{x.name} ({pct(x.soc_percent)})</option>)}
        </select>
      </label>
      <div className="two">
        <label className="field"><span>Datum</span><input type="date" value={form.date} onChange={set('date')} required /></label>
        <label className="field"><span>Uhrzeit</span><input type="time" value={form.time} onChange={set('time')} required /></label>
      </div>
      <label className="field"><span>Notiz (optional)</span>
        <input type="text" value={form.note} onChange={set('note')} maxLength={200} placeholder="z. B. Ersatzakku mitnehmen" />
      </label>
      <p className={hint.warn ? 'hint warn' : 'hint'}>{hint.text}</p>
      {error && <p className="hint warn">{error}</p>}
      <button className="btn" type="submit" disabled={busy}>{busy ? 'Speichert …' : 'Termin speichern'}</button>
    </form>
  )
}

/* --- devices due next ---------------------------------------------------------------------- */
function DueNext({ devices, onSelect }) {
  const due = devices.filter(dueAt).sort((a, b) => new Date(dueAt(a)) - new Date(dueAt(b)))
  const without = devices.length - due.length
  return (
    <>
      {due.length ? (
        <ul className="soon">
          {due.slice(0, 6).map((d) => (
            <li key={d.device_id}>
              <button type="button" onClick={() => onSelect(dayKey(dueAt(d)))}>
                <BatteryLevel device={d} />
                <span className="info">
                  <span className="name">{d.name}</span>
                  <span className="meta">{[d.location, d.category].filter(Boolean).join(' · ') || d.device_id}</span>
                </span>
                <span className="when">{new Date(dueAt(d)) <= new Date() ? 'jetzt' : shortDay(dueAt(d))}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="hint">Für kein Gerät ist ein Ausfall absehbar.</p>
      )}
      {without > 0 && (
        <p className="hint" style={{ marginTop: 10 }}>
          {without} {without === 1 ? 'Gerät' : 'Geräte'} ohne Prognose: Spannung fällt nicht oder es fehlen Messwerte.
        </p>
      )}
    </>
  )
}

/* --- the page ---------------------------------------------------------------------------------- */
const EMPTY_FORM = { device: '', date: '', time: '08:00', note: '' }

export default function Calendar({ devices, me }) {
  const tech = me.role === 'techniker'
  const [params] = useSearchParams()
  const [month, setMonth] = useState(() => ({ y: new Date().getFullYear(), m: new Date().getMonth() }))
  const [sel, setSel] = useState(() => dayKey(new Date()))
  const [form, setForm] = useState({ ...EMPTY_FORM, date: dayKey(new Date()) })
  const [msg, setMsg] = useState('')
  const appts = usePolling(() => (tech ? api.appointments() : Promise.resolve([])), [tech])

  const list = devices ?? []
  const events = useMemo(() => buildEvents(list, appts.data ?? []), [list, appts.data])

  const select = (key) => {
    const d = parseKey(key)
    setSel(key)
    setMonth({ y: d.getFullYear(), m: d.getMonth() })
    if (tech) setForm((f) => ({ ...f, date: key }))
  }
  const plan = (d) => {
    const key = suggestedDay(d)
    select(key)
    setForm((f) => ({ ...f, device: d.device_id, date: key }))
    setMsg('')
  }

  // /kalender?g=101 (link from the detail page): jump to that device
  const g = params.get('g')
  useEffect(() => {
    const d = g && list.find((x) => x.device_id === g)
    if (!d) return
    if (tech) plan(d)
    else if (dueAt(d)) select(dayKey(dueAt(d)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [g, devices === null])

  const shiftMonth = (step) => {
    if (step === 0) return select(dayKey(new Date()))
    const d = new Date(month.y, month.m + step, 1)
    setMonth({ y: d.getFullYear(), m: d.getMonth() })
  }

  async function remove(a) {
    try {
      await api.deleteAppointment(a.id)
      setMsg('Termin gelöscht.')
      appts.refresh()
    } catch (err) {
      setMsg(`Löschen fehlgeschlagen: ${err.message}`)
    }
  }

  const saved = (a) => {
    setMsg(`Termin am ${shortDay(a.starts_at)} um ${hhmm(a.starts_at)} Uhr gespeichert.`)
    setForm({ ...EMPTY_FORM, date: dayKey(a.starts_at) })
    select(dayKey(a.starts_at))
    appts.refresh()
  }

  const selDate = parseKey(sel)
  return (
    <div className="scroll">
      <div className="page">
        <div className="d-head">
          <h1>Kalender</h1>
          <p>
            {tech
              ? 'Voraussichtliche Ausfälle Ihrer Geräte und Ihre eigenen Wechseltermine'
              : 'Voraussichtliche Batterie-Ausfälle aller Geräte'}
            , geschätzt aus dem Spannungstrend der letzten 72 Stunden
          </p>
        </div>
        {msg && <p className="msg" role="status">{msg}</p>}
        {appts.error && <p className="hint warn">Termine konnten nicht geladen werden: {appts.error.message}</p>}
        <div className="cal-wrap">
          <section className="card" aria-label="Monatsansicht">
            <div className="cal-head">
              <h2>{MONTHS[month.m]} {month.y}</h2>
              <button type="button" className="btn-s" onClick={() => shiftMonth(-1)} aria-label="Vorheriger Monat">‹</button>
              <button type="button" className="btn-s" onClick={() => shiftMonth(0)}>Heute</button>
              <button type="button" className="btn-s" onClick={() => shiftMonth(1)} aria-label="Nächster Monat">›</button>
            </div>
            <MonthGrid month={month} sel={sel} events={events} onSelect={select} />
            <p className="cal-legend">
              <span className="s-niedrig"><i className="dot" />wird kritisch</span>
              <span className="s-krit"><i className="dot" />voraussichtlich leer</span>
              {tech && <span className="appt"><i className="dot" />eigener Wechseltermin</span>}
            </p>
          </section>
          <div className="cal-side">
            <section className="card" aria-label="Ausgewählter Tag">
              <h2>{WEEKDAYS_LONG[selDate.getDay()]}, {selDate.getDate()}. {MONTHS[selDate.getMonth()]}</h2>
              <DayAgenda list={events[sel] ?? []} tech={tech} onPlan={plan} onDelete={remove} />
            </section>
            {tech && (
              <section className="card" aria-label="Wechseltermin eintragen">
                <h2>Wechseltermin eintragen</h2>
                <AppointmentForm devices={list} form={form} setForm={setForm} onSaved={saved} />
              </section>
            )}
            <section className="card" aria-label="Als Nächstes fällig">
              <h2>Als Nächstes fällig</h2>
              {devices ? <DueNext devices={list} onSelect={select} /> : <p className="hint">Lade …</p>}
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}
