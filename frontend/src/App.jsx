/*
 * THE FRAME OF THE WEB PAGE: header bar + which page to show for which address.
 *
 *   /               -> pages/Overview.jsx      (list of all devices + map)
 *   /geraete/101    -> pages/DeviceDetail.jsx  (one device: battery, chart, messages)
 *
 * It also loads the device list (every 5 minutes, see usePolling.js) and the
 * status rules (20 % / 50 % thresholds) once, and hands them to the pages.
 */

import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { api } from './api.js'
import { time } from './format.js'
import DeviceDetail from './pages/DeviceDetail.jsx'
import Overview from './pages/Overview.jsx'
import { usePolling } from './usePolling.js'

export default function App() {
  const devices = usePolling(api.devices)
  const [rules, setRules] = useState(null)

  useEffect(() => {
    api.statusRules().then(setRules).catch(() => setRules(null))
  }, [])

  return (
    <>
      <header className="top">
        <NavLink className="brand" to="/">
          <span className="lamp" aria-hidden="true"><i /><i /><i /></span>BatteryWatch
        </NavLink>
        <nav aria-label="Hauptnavigation">
          <NavLink to="/" end>Übersicht</NavLink>
        </nav>
        <div className="stamp">
          {devices.error && <span className="err">Backend nicht erreichbar: {devices.error.message}</span>}
          <span>Stand {time(devices.updatedAt)} · automatisch alle 5 Min.</span>
          <button type="button" className="btn-s" onClick={devices.refresh} disabled={devices.loading}>
            {devices.loading ? 'Lädt …' : 'Aktualisieren'}
          </button>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Overview devices={devices.data} rules={rules} />} />
          <Route path="/geraete/:id" element={<DeviceDetail rules={rules} />} />
          <Route path="*" element={<Overview devices={devices.data} rules={rules} />} />
        </Routes>
      </main>
    </>
  )
}
