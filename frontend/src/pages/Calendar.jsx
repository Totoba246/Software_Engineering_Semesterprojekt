/*
 * PAGE "Kalender" (address /kalender, optionally /kalender?g=101 to jump to a device)
 *
 *   F12 / issue #11  expected battery failures. Two entries per device, both calculated
 *                    by the server from the voltage trend of the last 72 h (GET /api/devices):
 *                      amber  "Wird kritisch"        estimated_critical_at (< 20 %)
 *                      red    "Voraussichtlich leer" estimated_empty_at    (0 %)
 *                    Admin/Mitarbeiter see all devices, Servicetechniker only
 *                    their own (the server filters the device list).
 *   F13 / issue #12  Servicetechniker enter PRIVATE appointments: when they want to
 *                    replace which battery (blue). Only they can see them
 *                    (GET/POST/PATCH/DELETE /api/appointments, other roles get 403).
 *                    A device may have several appointments.
 *
 * HOW THE PAGE IS BUILT
 *   "Jetzt fällig"   red box at the top: devices that are critical right now
 *   WEEK VIEW        the default, and the only view on phones: seven days with
 *                    every entry written out (what, when, which device, where)
 *                    and the actions right on it: Route (Google Maps),
 *                    "Wechsel einplanen" / "+ Weiterer Termin", "Bearbeiten", "Löschen".
 *                    Phone: a strip Mo-So to jump to a day, days stacked below.
 *                    Wide screen: seven columns next to each other.
 *   MONTH VIEW       wide screens only (switch "Woche | Monat"): the overview grid;
 *                    click a day to see its entries on the right.
 *   "Als Nächstes fällig"  upcoming devices; a click jumps to that week.
 *   Appointments are entered in a small dialog (components/AppointmentForm.jsx)
 *   that opens from "Wechsel einplanen" (device + suggested day prefilled),
 *   "+ Termin" on a day, or "Bearbeiten" on an appointment.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api.js'
import { AppointmentDialog, appointmentToForm } from '../components/AppointmentForm.jsx'
import { BatteryLevel } from '../components/Battery.jsx'
import RouteLink from '../components/RouteLink.jsx'
import { pct } from '../format.js'
import { usePolling } from '../usePolling.js'
import { addDays, DAY, dayKey, dueAt, hhmm, MONTHS, p2, parseKey, shortDay, suggestedDay, weekStart, WEEKDAYS_LONG } from '../dates.js'

const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

/* --- date helpers: see ../dates.js ------------------------------------------------------- */
// calendar week number (ISO 8601, as used in Germany)
function isoWeek(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7))
  return Math.ceil(((d - Date.UTC(d.getUTCFullYear(), 0, 1)) / DAY + 1) / 7)
}
function weekTitle(start) {
  const end = addDays(start, 6)
  const from = start.getMonth() === end.getMonth() ? `${start.getDate()}.` : `${start.getDate()}. ${MONTHS[start.getMonth()]}`
  return `${from} – ${end.getDate()}. ${MONTHS[end.getMonth()]} ${end.getFullYear()}`
}

/* --- small helpers ------------------------------------------------------------------------ */
// true while the screen is narrower than a tablet (re-evaluated when the window is resized/rotated)
function useIsPhone() {
  const query = '(max-width: 760px)'
  const [phone, setPhone] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const update = () => setPhone(mq.matches)
    mq.addEventListener('change', update)
    return () => mq.removeEventListener('change', update)
  }, [])
  return phone
}
// remembered per browser; storage can be unavailable (private window) -> just don't remember
function readPref(key) {
  try { return localStorage.getItem(key) } catch { return null }
}
function writePref(key, value) {
  try { localStorage.setItem(key, value) } catch { /* ignore */ }
}

const EVENT = {
  appt: { cls: 'appt', order: 0, label: 'Wechseltermin' },
  crit: { cls: 's-niedrig', order: 1, label: 'Wird kritisch' },
  empty: { cls: 's-krit', order: 2, label: 'Voraussichtlich leer' },
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
  return d ? <Link className="entry-name" to={`/geraete/${encodeURIComponent(d.device_id)}`}>{d.name}</Link>
    : <b className="entry-name">{fallback}</b>
}

/* --- one calendar entry, written out ---------------------------------------------------------- */
function Entry({ e, tech, planned, onPlan, onEdit, onDelete }) {
  const [confirm, setConfirm] = useState(false)
  if (e.type === 'appt') {
    const d = e.a.assigned ? e.d : null
    return (
      <li className="entry appt">
        <div className="entry-top"><span className="tag">Wechseltermin</span><b>{hhmm(e.at)} Uhr</b></div>
        <DeviceName d={d} fallback={e.a.device_name} />
        {d?.location && <span className="meta">{d.location} · Akku {pct(d.soc_percent)}</span>}
        {!e.a.assigned && <span className="meta warn">Gerät ist Ihnen nicht mehr zugeordnet</span>}
        {e.a.note && <span className="meta note">„{e.a.note}“</span>}
        <div className="entry-actions">
          {d && <RouteLink device={d} />}
          {!confirm && <button type="button" className="btn-s" onClick={() => onEdit(e.a)}>Bearbeiten</button>}
          {confirm ? (
            <>
              <button type="button" className="btn-s danger-solid" onClick={() => onDelete(e.a)}>Wirklich löschen</button>
              <button type="button" className="btn-s" onClick={() => setConfirm(false)}>Abbrechen</button>
            </>
          ) : (
            <button type="button" className="btn-s danger" onClick={() => setConfirm(true)}>Löschen</button>
          )}
        </div>
      </li>
    )
  }
  const past = new Date(e.at).getTime() <= Date.now()
  const what = e.type === 'crit' ? (past ? 'Bereits kritisch' : 'Wird kritisch') : (past ? 'Bereits leer' : 'Voraussichtlich leer')
  return (
    <li className={`entry ${EVENT[e.type].cls}`}>
      <div className="entry-top"><span className="tag">{what}</span>{!past && <b>ca. {hhmm(e.at)} Uhr</b>}</div>
      <DeviceName d={e.d} />
      <span className="meta">{[e.d.location, `Akku ${pct(e.d.soc_percent)}`].filter(Boolean).join(' · ')}</span>
      {tech ? (
        planned && <span className="meta ok">Ihr Termin: {shortDay(planned.starts_at)}, {hhmm(planned.starts_at)} Uhr</span>
      ) : (
        <span className="meta">
          {e.d.technician ? `Servicetechniker: ${e.d.technician.display_name}` : <span className="warn">Kein Servicetechniker zugeordnet</span>}
        </span>
      )}
      <div className="entry-actions">
        <RouteLink device={e.d} />
        {tech && <PlanButton planned={planned} onClick={() => onPlan(e.d)} />}
      </div>
    </li>
  )
}

// "Wechsel einplanen" - or, if the device already has an appointment, "Weiterer Termin"
function PlanButton({ planned, onClick }) {
  return planned
    ? <button type="button" className="btn-s" onClick={onClick} title="Weiteren Termin für dieses Gerät eintragen">+ Weiterer Termin</button>
    : <button type="button" className="btn-s plan-btn" onClick={onClick}>Wechsel einplanen</button>
}

function Entries({ list, ...rest }) {
  return (
    <ul className="entries">
      {list.map((e, i) => (
        <Entry key={e.type === 'appt' ? `a${e.a.id}` : `${e.type}${e.d.device_id}${i}`} e={e}
          planned={e.d ? rest.plannedFor[e.d.device_id] : null} {...rest} />
      ))}
    </ul>
  )
}

/* --- WEEK VIEW ------------------------------------------------------------------------------------
 * Phones: strip Mo-So on top (tap = jump to the day), the seven days stacked below.
 * Wide screens: seven columns (the strip is hidden by styles.css).                               */
function WeekView({ start, sel, events, tech, onSelect, onPlanDay, entryProps }) {
  const today = dayKey(new Date())
  const days = Array.from({ length: 7 }, (_, i) => addDays(start, i))
  const jump = (key) => {
    onSelect(key)
    document.getElementById(`tag-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  return (
    <>
      <div className="wk-strip" role="group" aria-label="Wochentag wählen">
        {days.map((date, i) => {
          const key = dayKey(date)
          const list = events[key] ?? []
          const cls = ['wk-chip', key === today && 'today', key === sel && 'sel'].filter(Boolean).join(' ')
          return (
            <button key={key} type="button" className={cls} aria-pressed={key === sel} onClick={() => jump(key)}
              aria-label={`${WEEKDAYS_LONG[date.getDay()]}, ${date.getDate()}. ${MONTHS[date.getMonth()]}: ${list.length} ${list.length === 1 ? 'Eintrag' : 'Einträge'}`}>
              <span>{WEEKDAYS[i]}</span>
              <b>{date.getDate()}</b>
              <span className="dots" aria-hidden="true">
                {list.slice(0, 4).map((e, j) => <i key={j} className={`dot ${EVENT[e.type].cls}`} />)}
              </span>
            </button>
          )
        })}
      </div>
      <div className="week">
        {days.map((date) => {
          const key = dayKey(date)
          const list = events[key] ?? []
          const cls = ['wday', key === today && 'today', key === sel && 'sel', key < today && 'past', !list.length && 'free']
            .filter(Boolean).join(' ')
          return (
            <section key={key} id={`tag-${key}`} className={cls} aria-label={`${WEEKDAYS_LONG[date.getDay()]}, ${date.getDate()}. ${MONTHS[date.getMonth()]}`}>
              <header className="wday-head">
                <span className="wday-name">{WEEKDAYS_LONG[date.getDay()]}</span>
                <span className="wday-date">{date.getDate()}.{p2(date.getMonth() + 1)}.</span>
                {key === today && <span className="today-tag">Heute</span>}
                {tech && key >= today && (
                  <button type="button" className="btn-s add" onClick={() => onPlanDay(key)}
                    title="Wechseltermin an diesem Tag eintragen"
                    aria-label={`Termin am ${date.getDate()}.${date.getMonth() + 1}. eintragen`}>+<span className="add-label"> Termin</span></button>
                )}
              </header>
              {list.length ? <Entries list={list} tech={tech} {...entryProps} /> : <p className="wday-free">Keine Einträge</p>}
            </section>
          )
        })}
      </div>
    </>
  )
}

/* --- MONTH VIEW (wide screens) ------------------------------------------------------------------- */
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
        const cls = ['cal-day', date.getMonth() !== month.m && 'out', key === today && 'today', key === sel && 'sel', key < today && 'past']
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
          </button>
        )
      })}
    </div>
  )
}

/* --- "Jetzt fällig": devices that are critical right now -------------------------------------------- */
function DueNow({ devices, tech, plannedFor, onPlan }) {
  const now = devices.filter((d) => d.status === 'krit').sort((a, b) => (a.soc_percent ?? 0) - (b.soc_percent ?? 0))
  if (!now.length) return null
  return (
    <section className="card due-now" aria-label="Jetzt fällig">
      <h2>Jetzt fällig: {now.length} {now.length === 1 ? 'Gerät' : 'Geräte'} mit kritischem Akku</h2>
      <ul className="due-list">
        {now.map((d) => {
          const planned = plannedFor[d.device_id]
          return (
            <li key={d.device_id}>
              <BatteryLevel device={d} />
              <span className="info">
                <DeviceName d={d} />
                <span className="meta">
                  {[d.location, d.category].filter(Boolean).join(' · ') || d.device_id}
                  {!tech && (d.technician ? ` · ${d.technician.display_name}` : ' · kein Servicetechniker')}
                </span>
                {planned && <span className="meta ok">Ihr Termin: {shortDay(planned.starts_at)}, {hhmm(planned.starts_at)} Uhr</span>}
              </span>
              <span className="entry-actions">
                <RouteLink device={d} />
                {tech && <PlanButton planned={planned} onClick={() => onPlan(d)} />}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/* --- devices due next (not critical yet) ----------------------------------------------------------- */
function DueNext({ devices, onSelect }) {
  const upcoming = devices.filter((d) => d.status !== 'krit' && dueAt(d)).sort((a, b) => new Date(dueAt(a)) - new Date(dueAt(b)))
  const without = devices.filter((d) => !dueAt(d) && d.status !== 'krit').length
  return (
    <>
      {upcoming.length ? (
        <ul className="soon">
          {upcoming.slice(0, 6).map((d) => (
            <li key={d.device_id}>
              <button type="button" onClick={() => onSelect(dayKey(dueAt(d)))} title="Im Kalender zeigen">
                <BatteryLevel device={d} />
                <span className="info">
                  <span className="name">{d.name}</span>
                  <span className="meta">{[d.location, d.category].filter(Boolean).join(' · ') || d.device_id}</span>
                </span>
                <span className="when">{shortDay(dueAt(d))}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="hint">Für kein weiteres Gerät ist ein Ausfall absehbar.</p>
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
export default function Calendar({ devices, me }) {
  const tech = me.role === 'techniker'
  const phone = useIsPhone()
  const [params] = useSearchParams()
  const [viewPref, setViewPref] = useState(() => (readPref('bw.calView') === 'month' ? 'month' : 'week'))
  const view = phone ? 'week' : viewPref // phones: always the week
  const [sel, setSel] = useState(() => dayKey(new Date()))
  const [dialog, setDialog] = useState(null) // values of the appointment form while it is open
  const [dialogTitle, setDialogTitle] = useState(null)
  const [msg, setMsg] = useState(null) // { text, warn }
  const appts = usePolling(() => (tech ? api.appointments() : Promise.resolve([])), [tech])
  const viewRef = useRef(null)

  const list = devices ?? []
  const events = useMemo(() => buildEvents(list, appts.data ?? []), [list, appts.data])
  // the next upcoming own appointment per device ("Ihr Termin: ..." instead of "Wechsel einplanen")
  const plannedFor = useMemo(() => {
    const out = {}
    const from = Date.now() - 3600e3
    for (const a of [...(appts.data ?? [])].sort((x, y) => new Date(x.starts_at) - new Date(y.starts_at))) {
      if (new Date(a.starts_at).getTime() > from && !out[a.device_id]) out[a.device_id] = a
    }
    return out
  }, [appts.data])

  const selDate = parseKey(sel)
  const start = weekStart(selDate)
  const month = { y: selDate.getFullYear(), m: selDate.getMonth() }

  const openDialog = (form, title = null) => { setMsg(null); setDialogTitle(title); setDialog(form) }
  const plan = (d) => openDialog({ device: d.device_id, date: suggestedDay(d), time: '08:00', note: '' },
    plannedFor[d.device_id] ? 'Weiteren Termin eintragen' : null)
  const planDay = (key) => openDialog({ device: '', date: key, time: '08:00', note: '' })
  const edit = (a) => openDialog({ ...appointmentToForm(a), deviceName: a.device_name })
  const showDay = (key) => { setSel(key); viewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }

  // /kalender?g=101 (link from the detail page): jump to the day that device is due
  const g = params.get('g')
  useEffect(() => {
    const d = g && list.find((x) => x.device_id === g)
    if (!d) return
    if (dueAt(d)) setSel(dayKey(dueAt(d)))  // planning itself is done on the detail page
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [g, devices === null])

  const shift = (step) => {
    if (step === 0) return setSel(dayKey(new Date()))
    if (view === 'week') return setSel(dayKey(addDays(selDate, 7 * step)))
    setSel(dayKey(new Date(month.y, month.m + step, 1)))
  }
  const setView = (v) => { setViewPref(v); writePref('bw.calView', v) }

  async function remove(a) {
    try {
      await api.deleteAppointment(a.id)
      setMsg({ text: 'Termin gelöscht.' })
      appts.refresh()
    } catch (err) {
      setMsg({ text: `Löschen fehlgeschlagen: ${err.message}`, warn: true })
    }
  }
  const saved = (a, changed) => {
    setDialog(null)
    setMsg({ text: `Termin am ${shortDay(a.starts_at)} um ${hhmm(a.starts_at)} Uhr ${changed ? 'geändert' : 'gespeichert'}.` })
    setSel(dayKey(a.starts_at))
    appts.refresh()
  }

  const entryProps = { plannedFor, onPlan: plan, onEdit: edit, onDelete: remove }
  const dayList = events[sel] ?? []
  const weekEmpty = Array.from({ length: 7 }, (_, i) => events[dayKey(addDays(start, i))]).every((l) => !l)
  const thisWeek = dayKey(start) === dayKey(weekStart(new Date()))

  return (
    <div className="scroll">
      <div className="page cal-page">
        <div className="d-head">
          <h1>Kalender</h1>
          <p>{tech ? 'Voraussichtliche Ausfälle Ihrer Geräte und Ihre Wechseltermine' : 'Voraussichtliche Batterie-Ausfälle aller Geräte'}</p>
        </div>
        {msg && <p className={msg.warn ? 'notice warn' : 'msg'} role="status">{msg.text}</p>}
        {appts.error && <p className="notice warn">Termine konnten nicht geladen werden: {appts.error.message}</p>}

        <DueNow devices={list} tech={tech} plannedFor={plannedFor} onPlan={plan} />

        <div className={`cal-wrap view-${view}`}>
          <section className="card cal-main" aria-label={view === 'week' ? 'Wochenansicht' : 'Monatsansicht'} ref={viewRef}>
            <div className="cal-head">
              <h2>
                {view === 'week' ? weekTitle(start) : `${MONTHS[month.m]} ${month.y}`}
                {view === 'week' && <small>KW {isoWeek(start)}{thisWeek && ' · diese Woche'}</small>}
              </h2>
              <div className="cal-nav">
                <button type="button" className="btn-s" onClick={() => shift(-1)} aria-label={view === 'week' ? 'Vorherige Woche' : 'Vorheriger Monat'}>‹</button>
                <button type="button" className="btn-s" onClick={() => shift(0)}>Heute</button>
                <button type="button" className="btn-s" onClick={() => shift(1)} aria-label={view === 'week' ? 'Nächste Woche' : 'Nächster Monat'}>›</button>
              </div>
              {!phone && (
                <div className="seg small" role="group" aria-label="Ansicht">
                  <button type="button" aria-pressed={view === 'week'} onClick={() => setView('week')}>Woche</button>
                  <button type="button" aria-pressed={view === 'month'} onClick={() => setView('month')}>Monat</button>
                </div>
              )}
              {tech && <button type="button" className="btn btn-sm" onClick={() => planDay(sel >= dayKey(new Date()) ? sel : dayKey(new Date()))}>+ Termin</button>}
            </div>

            {view === 'week' ? (
              <>
                <WeekView start={start} sel={sel} events={events} tech={tech} onSelect={setSel} onPlanDay={planDay} entryProps={entryProps} />
                {weekEmpty && devices && (
                  <p className="hint week-empty">In dieser Woche ist kein Ausfall absehbar{tech ? ' und kein Termin eingetragen' : ''}.</p>
                )}
              </>
            ) : (
              <MonthGrid month={month} sel={sel} events={events} onSelect={setSel} />
            )}
            <p className="cal-legend">
              <span className="s-niedrig"><i className="dot" />wird kritisch (unter 20 %)</span>
              <span className="s-krit"><i className="dot" />voraussichtlich leer</span>
              {tech && <span className="appt"><i className="dot" />eigener Wechseltermin</span>}
              <span>Schätzung aus dem Spannungstrend der letzten 72 Std.</span>
            </p>
          </section>

          <div className="cal-side">
            {view === 'month' && (
              <section className="card" aria-label="Ausgewählter Tag">
                <div className="card-head">
                  <h2>{WEEKDAYS_LONG[selDate.getDay()]}, {selDate.getDate()}. {MONTHS[selDate.getMonth()]}</h2>
                  {tech && sel >= dayKey(new Date()) && <button type="button" className="btn-s" onClick={() => planDay(sel)}>+ Termin</button>}
                </div>
                {dayList.length ? <Entries list={dayList} tech={tech} {...entryProps} />
                  : <p className="hint">Keine {tech ? 'Ausfälle oder Termine' : 'voraussichtlichen Ausfälle'} an diesem Tag.</p>}
              </section>
            )}
            <section className="card" aria-label="Als Nächstes fällig">
              <h2>Als Nächstes fällig</h2>
              {devices ? <DueNext devices={list} onSelect={showDay} /> : <p className="hint">Lade …</p>}
            </section>
          </div>
        </div>
      </div>

      {dialog && (
        <AppointmentDialog title={dialogTitle} devices={list} form={dialog} setForm={setDialog}
          onSaved={saved} onCancel={() => setDialog(null)} />
      )}
    </div>
  )
}
