/*
 * FORM FOR DEVICE MASTER DATA (F07) + technician assignment (F09).
 * Used to add a node (pages/NewDevice.jsx) and to edit one (DeviceDetail.jsx).
 * Only Firmenchef/Mitarbeiter see it; the server checks that again.
 * No coordinates: the position always comes from the node's GPS.
 */
import { useEffect, useState } from 'react'
import { api } from '../api.js'

// Suggestions from the GUI draft; any other text is allowed too
const CATEGORIES = ['Baustellenampel', 'Geschwindigkeitsanzeige', 'Verkehrszählgerät', 'Warnleitanhänger', 'Messanhänger']

const toInput = (v) => (v == null ? '' : String(v))

export default function DeviceForm({ device, onSubmit, onCancel, submitLabel = 'Speichern' }) {
  const isNew = !device
  const [form, setForm] = useState({
    device_id: '',
    name: device && device.name !== device.device_id ? device.name : '',
    category: toInput(device?.category),
    location: toInput(device?.location),
    technician_id: toInput(device?.technician?.id),
  })
  const [technicians, setTechnicians] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.technicians().then(setTechnicians).catch(() => setTechnicians([]))
  }, [])

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    const data = {
      name: form.name, category: form.category, location: form.location,
      technician_id: form.technician_id ? Number(form.technician_id) : null,
    }
    if (isNew) data.device_id = form.device_id.trim()
    setBusy(true)
    setError('')
    try {
      await onSubmit(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      {isNew && (
        <label className="field">
          <span>Geräte-ID (wie im MQTT-Topic)</span>
          <input type="text" value={form.device_id} onChange={set('device_id')} required placeholder="z. B. 101" pattern="[A-Za-z0-9_.\-]{1,64}" />
          <small className="hint">Node 101 sendet an traffic-nodes/<b>101</b>/measurements → Geräte-ID 101. Seine Nachrichten landen dann automatisch bei diesem Gerät.</small>
        </label>
      )}
      <label className="field">
        <span>Name</span>
        <input type="text" value={form.name} onChange={set('name')} maxLength={100} placeholder="z. B. BA-01 Hauptstraße" />
      </label>
      <div className="two">
        <label className="field">
          <span>Kategorie</span>
          <input type="text" list="categories" value={form.category} onChange={set('category')} maxLength={60} />
          <datalist id="categories">{CATEGORIES.map((c) => <option key={c} value={c} />)}</datalist>
        </label>
        <label className="field">
          <span>Ort</span>
          <input type="text" value={form.location} onChange={set('location')} maxLength={120} placeholder="z. B. Rottweil" />
        </label>
      </div>
      <p className="hint">Die Position auf der Karte kommt automatisch vom GPS des Geräts (Durchschnitt der letzten Tage).</p>
      <label className="field">
        <span>Zugeordneter Servicetechniker</span>
        <select value={form.technician_id} onChange={set('technician_id')}>
          <option value="">– niemand –</option>
          {technicians.map((t) => <option key={t.id} value={t.id}>{t.display_name}</option>)}
        </select>
      </label>
      {error && <p className="hint warn" role="alert">{error}</p>}
      <div className="row-btns">
        <button className="btn" type="submit" disabled={busy}>{submitLabel}</button>
        {onCancel && <button className="btn-s" type="button" onClick={onCancel}>Abbrechen</button>}
      </div>
    </form>
  )
}
