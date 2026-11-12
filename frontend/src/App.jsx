/*
 * THE FRAME OF THE WEB PAGE: who is logged in, header bar, which page to show.
 *
 *   not logged in             -> pages/Login.jsx
 *   start password            -> must choose an own password first
 *   Admin                     -> pages/UserAdmin.jsx (user management only, no devices)
 *   Firmenchef / Mitarbeiter  -> /              all devices (Overview) + "Gerät hinzufügen"
 *                                /geraete/101   detail page, master data editable
 *                                /geraete/neu   add a node
 *                                /kalender      expected failures of all devices (F12)
 *   Servicetechniker          -> the same pages, but only their assigned devices
 *                                (the SERVER filters - see backend/batterywatch/api/devices.py);
 *                                /kalender also shows their private appointments (F13)
 */

import { useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { api, isManagement, ROLES } from './api.js'
import PasswordForm from './components/PasswordForm.jsx'
import { time } from './format.js'
import Calendar from './pages/Calendar.jsx'
import DeviceDetail from './pages/DeviceDetail.jsx'
import Login from './pages/Login.jsx'
import NewDevice from './pages/NewDevice.jsx'
import Overview from './pages/Overview.jsx'
import UserAdmin from './pages/UserAdmin.jsx'
import { usePolling } from './usePolling.js'

export default function App() {
  const [me, setMe] = useState(undefined) // undefined = still checking, null = not logged in

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null))
    const loggedOut = () => setMe(null) // fired by api.js on any 401
    window.addEventListener('bw:unauthorized', loggedOut)
    return () => window.removeEventListener('bw:unauthorized', loggedOut)
  }, [])

  const logout = async () => {
    await api.logout().catch(() => {})
    setMe(null)
  }

  if (me === undefined) return <div className="center-page"><p className="hint">Lade …</p></div>
  if (!me) return <Login onLogin={setMe} />
  if (me.must_change_password) {
    return (
      <div className="center-page">
        <section className="card login">
          <h2>Eigenes Passwort festlegen</h2>
          <PasswordForm forced onDone={() => api.me().then(setMe)} />
          <button type="button" className="reset" onClick={logout}>Abmelden</button>
        </section>
      </div>
    )
  }
  return me.role === 'admin' ? <AdminShell me={me} onLogout={logout} /> : <DeviceShell me={me} onLogout={logout} />
}

/* --- header with user menu -------------------------------------------------------- */
function Header({ me, onLogout, children, nav }) {
  const [menu, setMenu] = useState(false)
  const [pwd, setPwd] = useState(false)
  const [saved, setSaved] = useState(false)
  return (
    <header className="top">
      <NavLink className="brand" to="/">
        <span className="lamp" aria-hidden="true"><i /><i /><i /></span>BatteryWatch
      </NavLink>
      <nav aria-label="Hauptnavigation">{nav}</nav>
      <div className="stamp">{children}</div>
      <div className="usermenu">
        <button type="button" className="who" aria-expanded={menu} onClick={() => setMenu(!menu)}>
          <span className="av">{initials(me.display_name)}</span>
          <span><b>{me.display_name}</b><small>{ROLES[me.role]}</small></span>
        </button>
        {menu && (
          <div className="menu float" role="menu">
            <button type="button" role="menuitem" onClick={() => { setPwd(true); setMenu(false) }}>Passwort ändern</button>
            <button type="button" role="menuitem" onClick={onLogout}>Abmelden</button>
          </div>
        )}
      </div>
      {pwd && (
        <div className="overlay" role="dialog" aria-modal="true" aria-label="Passwort ändern">
          <section className="card dialog">
            <h2>Passwort ändern</h2>
            <PasswordForm onDone={() => { setPwd(false); setSaved(true) }} onCancel={() => setPwd(false)} />
          </section>
        </div>
      )}
      {saved && <p className="toast" onAnimationEnd={() => setSaved(false)}>Passwort gespeichert.</p>}
    </header>
  )
}

const initials = (name) => name.split(/\s+/).filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase()

/* --- Admin: only the user management --------------------------------------------------- */
function AdminShell({ me, onLogout }) {
  return (
    <>
      <Header me={me} onLogout={onLogout} nav={<NavLink to="/" end>Nutzerverwaltung</NavLink>} />
      <main>
        <Routes>
          <Route path="/" element={<UserAdmin me={me} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  )
}

/* --- Firmenchef / Mitarbeiter / Servicetechniker: devices ------------------------------ */
function DeviceShell({ me, onLogout }) {
  const devices = usePolling(api.devices) // every 5 minutes (ADR-06)
  const [rules, setRules] = useState(null)
  useEffect(() => {
    api.statusRules().then(setRules).catch(() => setRules(null))
  }, [])
  const manager = isManagement(me)

  return (
    <>
      <Header me={me} onLogout={onLogout}
        nav={<>
          <NavLink to="/" end>{me.role === 'techniker' ? 'Meine Geräte' : 'Übersicht'}</NavLink>
          <NavLink to="/kalender">Kalender</NavLink>
        </>}>
        {devices.error && <span className="err">Backend nicht erreichbar: {devices.error.message}</span>}
        <span>Stand {time(devices.updatedAt)} · automatisch alle 5 Min.</span>
        <button type="button" className="btn-s" onClick={devices.refresh} disabled={devices.loading}>
          {devices.loading ? 'Lädt …' : 'Aktualisieren'}
        </button>
      </Header>
      <Alerts devices={devices.data} me={me} />
      <main>
        <Routes>
          <Route path="/" element={<Overview devices={devices.data} rules={rules} me={me} />} />
          <Route path="/geraete/neu" element={manager ? <NewDevice onSaved={devices.refresh} /> : <Navigate to="/" replace />} />
          <Route path="/kalender" element={<Calendar devices={devices.data} me={me} />} />
          <Route path="/geraete/:id" element={<DeviceDetail rules={rules} me={me} onChanged={devices.refresh} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  )
}

/* --- warning banner (F02 / issue #7, in-app part) --------------------------------------- */
function Alerts({ devices, me }) {
  if (!devices) return null
  const critical = devices.filter((d) => d.status === 'krit')
  const broken = devices.filter((d) => d.last_message_error)
  if (!critical.length && !broken.length) return null
  const names = (list) => list.slice(0, 3).map((d) => d.name).join(', ') + (list.length > 3 ? ' …' : '')
  return (
    <div className="alerts" role="status">
      {critical.length > 0 && (
        <span className="s-krit"><i className="dot" />
          <span>
            <b>{critical.length} {critical.length === 1 ? 'Gerät' : 'Geräte'} mit kritischem Akkustand</b>
            {me.role === 'techniker' && ' (Ihnen zugeordnet)'}: {names(critical)}
          </span>
          <Link to="/?status=krit">anzeigen</Link>
        </span>
      )}
      {broken.length > 0 && (
        <span className="s-unbekannt"><i className="dot" />
          {broken.length} {broken.length === 1 ? 'Gerät sendet' : 'Geräte senden'} ungültige Werte: {names(broken)}
        </span>
      )}
    </div>
  )
}
