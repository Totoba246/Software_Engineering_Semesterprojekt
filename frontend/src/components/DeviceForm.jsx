/*
 * FORM FOR DEVICE MASTER DATA (F07) + technician assignment (F09).
 * Used to add a node (pages/NewDevice.jsx) and to edit one (DeviceDetail.jsx).
 * Only Firmenchef/Mitarbeiter see it; the server checks that again.
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
    // only a MANUAL position is editable; a GPS position comes from the node itself
    latitude: device?.position?.source === 'manuell' ? toInput(device.position.latitude) : '',
    longitude: device?.position?.source === 'manuell' ? toInput(device.position.longitude) : '',
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
    const number = (v) => (v.trim() === '' ? null : Number(v.replace(',', '.')))
    const data = {
      name: form.name, category: form.category, location: form.location,
      technician_id: form.technician_id ? Number(form.technician_id) : null,
    }
    if (isNew) data.device_id = form.device_id.trim()
    if (isNew || device.position?.source !== 'gps') {
      data.latitude = number(form.latitude)
      data.longitude = number(form.longitude)
      if (Number.isNaN(data.latitude) || Number.isNaN(data.longitude)) return setError('Koordinaten bitte als Zahl, z. B. 48.168')
    }
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
      {isNew || device.position?.source !== 'gps' ? (
        <div className="two">
          <label className="field">
            <span>Breitengrad (ohne GPS)</span>
            <input type="text" inputMode="decimal" value={form.latitude} onChange={set('latitude')} placeholder="48.168" />
          </label>
          <label className="field">
            <span>Längengrad (ohne GPS)</span>
            <input type="text" inputMode="decimal" value={form.longitude} onChange={set('longitude')} placeholder="8.628" />
          </label>
        </div>
      ) : (
        <p className="hint">Position kommt per GPS vom Gerät.</p>
      )}
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
