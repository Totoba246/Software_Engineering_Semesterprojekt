/*
 * FORM FOR A PRIVATE REPLACEMENT APPOINTMENT (Servicetechniker, F13), in a dialog.
 * Used by the calendar (pages/Calendar.jsx) and the device detail page.
 *
 *   new appointment   form = { device, date, time, note }        -> POST  /api/appointments
 *   edit appointment  form = { id, device, date, time, note }    -> PATCH /api/appointments/<id>
 *                     (the device can't be changed; to move the visit to another
 *                      device, delete it and enter a new one)
 * A device may have SEVERAL appointments (e.g. check first, replace later).
 * The form warns when the chosen day is in the past or after the predicted
 * critical/empty date, but saving is still allowed.
 */
import { useState } from 'react'
import { api } from '../api.js'
import { dayKey, dueAt, hhmm, shortDay } from '../dates.js'
import { pct } from '../format.js'

// appointment from the API -> values of the form (for "Bearbeiten")
export const appointmentToForm = (a) => ({
  id: a.id, device: a.device_id, date: dayKey(a.starts_at), time: hhmm(a.starts_at), note: a.note ?? '',
})

export default function AppointmentForm({ devices, form, setForm, onSaved, onCancel }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })
  const editing = form.id != null

  if (!devices.length && !editing) {
    return (
      <>
        <p className="hint">Ihnen sind noch keine Geräte zugeordnet.</p>
        <button className="btn-s" type="button" onClick={onCancel}>Schließen</button>
      </>
    )
  }

  // warnings: too late or in the past (saving is still allowed)
  const d = devices.find((x) => x.device_id === form.device)
  let hint = null
  if (form.date && form.date < dayKey(new Date())) hint = 'Das Datum liegt in der Vergangenheit.'
  else if (d?.estimated_empty_at && form.date > dayKey(d.estimated_empty_at)) {
    hint = `Achtung: Das Gerät ist voraussichtlich schon am ${shortDay(d.estimated_empty_at)} leer.`
  } else if (d?.estimated_critical_at && form.date > dayKey(d.estimated_critical_at)) {
    hint = `Hinweis: Der Akku ist voraussichtlich ab ${shortDay(d.estimated_critical_at)} kritisch.`
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
      const saved = editing
        ? await api.updateAppointment(form.id, { starts_at, note: form.note })
        : await api.createAppointment({ device_id: form.device, starts_at, note: form.note })
      onSaved(saved, editing)
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
        <select value={form.device} onChange={set('device')} required disabled={editing || devices.length === 1}>
          <option value="">Gerät wählen</option>
          {sorted.map((x) => <option key={x.device_id} value={x.device_id}>{x.name} ({pct(x.soc_percent)})</option>)}
          {editing && !d && <option value={form.device}>{form.deviceName ?? form.device}</option>}
        </select>
      </label>
      <div className="two">
        <label className="field"><span>Datum</span><input type="date" value={form.date} onChange={set('date')} required /></label>
        <label className="field"><span>Uhrzeit</span><input type="time" value={form.time} onChange={set('time')} required /></label>
      </div>
      <label className="field"><span>Notiz (optional)</span>
        <input type="text" value={form.note} onChange={set('note')} maxLength={200} placeholder="z. B. Ersatzakku mitnehmen" />
      </label>
      {hint ? <p className="notice warn">{hint}</p> : <p className="hint">Termine sind privat und nur für Sie sichtbar.</p>}
      {error && <p className="notice warn" role="alert">{error}</p>}
      <div className="row-btns">
        <button className="btn" type="submit" disabled={busy}>{busy ? 'Speichert …' : editing ? 'Änderung speichern' : 'Termin speichern'}</button>
        <button className="btn-s" type="button" onClick={onCancel}>Abbrechen</button>
      </div>
    </form>
  )
}

/* The form in a dialog (on phones a sheet from the bottom, see .overlay.sheet in styles.css).
 * title: e.g. "Weiteren Termin eintragen" when the device already has one. */
export function AppointmentDialog({ title, ...props }) {
  const heading = title ?? (props.form.id != null ? 'Termin bearbeiten' : 'Wechseltermin eintragen')
  return (
    <div className="overlay sheet" role="dialog" aria-modal="true" aria-label={heading}
      onClick={(e) => { if (e.target === e.currentTarget) props.onCancel() }}>
      <section className="card dialog">
        <h2>{heading}</h2>
        <AppointmentForm {...props} />
      </section>
    </div>
  )
}
