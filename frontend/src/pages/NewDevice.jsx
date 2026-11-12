/*
 * PAGE "Gerät hinzufügen" (/geraete/neu, Firmenchef/Mitarbeiter only).
 * Registers a node in advance - e.g. to give it a name, place and technician
 * before its first message. Nodes that just start sending are added
 * automatically by the collector anyway.
 */
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import DeviceForm from '../components/DeviceForm.jsx'

export default function NewDevice({ onSaved }) {
  const navigate = useNavigate()
  return (
    <div className="scroll">
      <div className="detail narrow">
        <Link className="back" to="/">← Zur Übersicht</Link>
        <div className="d-head"><h1>Gerät hinzufügen</h1></div>
        <section className="card">
          <DeviceForm
            submitLabel="Gerät anlegen"
            onCancel={() => navigate('/')}
            onSubmit={async (data) => {
              const device = await api.createDevice(data)
              onSaved?.()
              navigate(`/geraete/${encodeURIComponent(device.device_id)}`)
            }}
          />
        </section>
      </div>
    </div>
  )
}
