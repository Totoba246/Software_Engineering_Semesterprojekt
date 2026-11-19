/*
 * THE FRAME OF THE WEB PAGE: who is logged in, header bar, which page to show.
 *
 *   not logged in        -> pages/Login.jsx
 *   start password       -> must choose an own password first
 *   Admin, Mitarbeiter   -> /              all devices (Overview) + "Gerät hinzufügen"
 *                           /geraete/101   detail page, master data editable
 *                           /geraete/neu   add a node
 *                           /kalender      expected failures of all devices (F12)
 *                           /verwaltung    "Verwaltung": devices as a table (both roles),
 *                                          categories and user accounts (Admin only)
 *   Servicetechniker     -> the same device pages, but only their assigned devices
 *                           (the SERVER filters - see backend/batterywatch/api/devices.py);
 *                           /kalender also shows their private appointments (F13)
 * The Admin is the Firmenchef: same views as a Mitarbeiter plus the admin pages.
 */

import { useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { api, isAdmin, isManagement, ROLES } from './api.js'
import PasswordForm from './components/PasswordForm.jsx'
import { time } from './format.js'
import Calendar from './pages/Calendar.jsx'
import DeviceDetail from './pages/DeviceDetail.jsx'
import Login from './pages/Login.jsx'
import { CategoryAdmin, DeviceAdmin, Manage } from './pages/Manage.jsx'
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
  return <DeviceShell me={me} onLogout={logout} />
}

/* --- header with user menu -------------------------------------------------------- */
/* small inline icons (take the text colour) for the phone tab bar, the refresh button and warnings */
const Icon = ({ d, size = 20 }) => (
  <svg className="ic" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
)
const ICONS = {
  devices: 'M7 7h10a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Zm14 4v2M9 10v4m3-4v4',
  calendar: 'M7 3v4m10-4v4M4 9h16M6 5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z',
  refresh: 'M20 11a8 8 0 0 0-14.9-3M4 4v4h4m-4 5a8 8 0 0 0 14.9 3M20 20v-4h-4',
  warn: 'M12 9v4m0 4h.01M10.3 3.9 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  manage: 'M4 6h9m4 0h3M4 12h3m4 0h9M4 18h11m4 0h1M15 4v4M9 10v4m8 2v4',
}

/*
 * Header bar. On phones (see "Phone layout" in styles.css) it shrinks to one
 * row (logo + refresh + avatar) and the navigation moves to a tab bar at the
 * BOTTOM of the screen, where the thumb reaches it.
 */
function Header({ me, onLogout, children, nav }) {
  const [menu, setMenu] = useState(false)
  const [pwd, setPwd] = useState(false)
  const [saved, setSaved] = useState(false)
  return (
    <header className="top">
      <NavLink className="brand" to="/" aria-label="BatteryWatch, zur Startseite">
        <span className="lamp" aria-hidden="true"><i /><i /><i /></span>BatteryWatch
      </NavLink>
      <nav aria-label="Hauptnavigation">{nav}</nav>
      <div className="stamp">{children}</div>
      <div className="usermenu">
        <button type="button" className="who" aria-expanded={menu} onClick={() => setMenu(!menu)}
          title={`${me.display_name} (${ROLES[me.role]})`}>
          <span className="av">{initials(me.display_name)}</span>
          <span><b>{me.display_name}</b><small>{ROLES[me.role]}</small></span>
        </button>
        {menu && (
          <div className="menu float" role="menu">
            {/* on narrow screens the header shows only the avatar - the name is repeated here */}
            <p className="menu-who"><b>{me.display_name}</b><small>{ROLES[me.role]}</small></p>
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

/* --- the same frame for every role; what is shown depends on the role ------------------ */
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
          <NavLink to="/" end><Icon d={ICONS.devices} /><span>{me.role === 'techniker' ? 'Meine Geräte' : 'Übersicht'}</span></NavLink>
          <NavLink to="/kalender"><Icon d={ICONS.calendar} /><span>Kalender</span></NavLink>
          {manager && <NavLink to="/verwaltung"><Icon d={ICONS.manage} /><span>Verwaltung</span></NavLink>}
        </>}>
        {devices.error && <span className="err">Backend nicht erreichbar: {devices.error.message}</span>}
        <span className="stamp-text">Stand {time(devices.updatedAt)}<span className="wide-only"> · automatisch alle 5 Min.</span></span>
        <button type="button" className="btn-s refresh" onClick={devices.refresh} disabled={devices.loading}
          title="Daten jetzt aktualisieren" aria-label="Daten jetzt aktualisieren">
          <Icon d={ICONS.refresh} size={16} /><span className="wide-only">{devices.loading ? 'Lädt …' : 'Aktualisieren'}</span>
        </button>
      </Header>
      <Alerts devices={devices.data} me={me} />
      <main>
        <Routes>
          <Route path="/" element={<Overview devices={devices.data} rules={rules} me={me} />} />
          <Route path="/geraete/neu" element={manager ? <NewDevice onSaved={devices.refresh} /> : <Navigate to="/" replace />} />
          <Route path="/kalender" element={<Calendar devices={devices.data} me={me} />} />
          <Route path="/geraete/:id" element={<DeviceDetail rules={rules} me={me} onChanged={devices.refresh} />} />
          {manager && (
            <Route path="/verwaltung" element={<Manage me={me} />}>
              <Route index element={<Navigate to="geraete" replace />} />
              <Route path="geraete" element={<DeviceAdmin devices={devices.data} me={me} onChanged={devices.refresh} />} />
              {isAdmin(me) && <Route path="kategorien" element={<CategoryAdmin onChanged={devices.refresh} />} />}
              {isAdmin(me) && <Route path="nutzer" element={<UserAdmin me={me} />} />}
            </Route>
          )}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  )
}

/* --- warning banner (F02 / issue #7, in-app part) ---------------------------------------
 * Coloured strips right below the header, so they can't be overlooked:
 *   red    devices with a critical battery -> the whole strip is a link to them
 *   amber  devices sending invalid values (e.g. sensor read error)
 */
function Alerts({ devices, me }) {
  if (!devices) return null
  const critical = devices.filter((d) => d.status === 'krit')
  const broken = devices.filter((d) => d.last_message_error)
  if (!critical.length && !broken.length) return null
  const names = (list) => list.slice(0, 3).map((d) => d.name).join(', ') + (list.length > 3 ? ` und ${list.length - 3} weitere` : '')
  return (
    <div className="alerts" role="status">
      {critical.length > 0 && (
        <Link className="al al-krit" to="/?status=krit">
          <Icon d={ICONS.warn} />
          <span className="al-text">
            <b>{critical.length} {critical.length === 1 ? 'Gerät' : 'Geräte'} mit kritischem Akkustand</b>
            {me.role === 'techniker' && <span className="wide-only"> (Ihnen zugeordnet)</span>}
            <span className="al-names">{names(critical)}</span>
          </span>
          <span className="al-go">Anzeigen ›</span>
        </Link>
      )}
      {broken.length > 0 && (
        <div className="al al-warn">
          <Icon d={ICONS.warn} />
          <span className="al-text">
            <b>{broken.length} {broken.length === 1 ? 'Gerät sendet' : 'Geräte senden'} ungültige Werte</b>
            <span className="al-names">{names(broken)}</span>
          </span>
        </div>
      )}
    </div>
  )
}
