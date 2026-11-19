/*
 * PAGE "Verwaltung" (/verwaltung/...), for the office:
 *
 *   Geräte      /verwaltung/geraete     Admin + Mitarbeiter: all devices as a table;
 *                                       category and technician can be changed right
 *                                       in the table, name/place in a dialog; delete
 *   Kategorien  /verwaltung/kategorien  Admin: create, rename, delete device categories
 *   Nutzer      /verwaltung/nutzer      Admin: user accounts (pages/UserAdmin.jsx)
 *
 * The Admin is the Firmenchef: apart from these pages they use the same views
 * as a Mitarbeiter (overview, detail, calendar). The server checks every change
 * again (backend/batterywatch/api/devices.py, categories.py, users.py).
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { api, isAdmin } from '../api.js'
import { BatteryLevel } from '../components/Battery.jsx'
import DeviceForm from '../components/DeviceForm.jsx'
import { ago } from '../format.js'

/* --- frame with the tabs ------------------------------------------------------------------ */
export function Manage({ me }) {
  const tabs = [['geraete', 'Geräte'], ...(isAdmin(me) ? [['kategorien', 'Kategorien'], ['nutzer', 'Nutzer']] : [])]
  return (
    <div className="scroll">
      <div className="page">
        <div className="d-head"><h1>Verwaltung</h1></div>
        {tabs.length > 1 && (
          <nav className="tabs" aria-label="Bereiche der Verwaltung">
            {tabs.map(([path, label]) => <NavLink key={path} to={path}>{label}</NavLink>)}
          </nav>
        )}
        <Outlet />
      </div>
    </div>
  )
}

/* --- Geräte ------------------------------------------------------------------------------- */
export function DeviceAdmin({ devices, onChanged }) {
  const [technicians, setTechnicians] = useState([])
  const [categories, setCategories] = useState([])
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState(null) // device in the edit dialog
  const [pendingDelete, setPendingDelete] = useState(null)
  const [msg, setMsg] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.technicians().then(setTechnicians).catch(() => setTechnicians([]))
    api.categories().then(setCategories).catch(() => setCategories([]))
  }, [])

  const all = devices ?? []
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return all
      .filter((d) => !q || [d.name, d.device_id, d.location, d.category, d.technician?.display_name]
        .some((v) => v?.toLowerCase().includes(q)))
      .sort((a, b) => a.name.localeCompare(b.name, 'de'))
  }, [all, query])

  async function change(d, data, text) {
    setError('')
    try {
      await api.updateDevice(d.device_id, data)
      setMsg(text)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }
  async function remove(d) {
    setError('')
    try {
      await api.deleteDevice(d.device_id)
      setMsg(`${d.name} wurde mit allen Messwerten gelöscht.`)
      setPendingDelete(null)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const stats = [
    [all.length, 'Geräte gesamt'],
    [all.filter((d) => !d.technician).length, 'ohne Servicetechniker'],
    [all.filter((d) => !d.category).length, 'ohne Kategorie'],
    [all.filter((d) => d.stale).length, 'ohne aktuelle Meldung'],
  ]

  return (
    <>
      <p className="lead">Stammdaten aller Geräte: Kategorie und Servicetechniker direkt in der Tabelle ändern, Name und Ort über „Bearbeiten“.</p>
      {msg && <p className="msg" role="status">{msg}</p>}
      {error && <p className="notice warn" role="alert">{error}</p>}
      <div className="stats">{stats.map(([n, l]) => <div className="stat" key={l}><b>{n}</b><span>{l}</span></div>)}</div>

      <section className="card" aria-label="Alle Geräte">
        <div className="card-head">
          <h2>Alle Geräte</h2>
          <div className="tbl-filters">
            <input type="search" placeholder="Name, ID, Ort, Techniker" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Geräte suchen" />
            <Link className="btn btn-sm" to="/geraete/neu">+ Gerät hinzufügen</Link>
          </div>
        </div>
        {!devices && <p className="hint">Lade …</p>}
        <table className="users dev-tbl">
          <thead><tr><th>Gerät</th><th>Kategorie</th><th>Servicetechniker</th><th>Letzte Meldung</th><th><span className="sr">Aktionen</span></th></tr></thead>
          <tbody>
            {shown.map((d) => (
              <tr key={d.device_id}>
                <td><div className="u">
                  <BatteryLevel device={d} />
                  <div>
                    <Link to={`/geraete/${encodeURIComponent(d.device_id)}`}><b>{d.name}</b></Link>
                    <span className="meta">{[d.name !== d.device_id && `ID ${d.device_id}`, d.location].filter(Boolean).join(' · ') || '–'}</span>
                  </div>
                </div></td>
                <td>
                  <select className="role-sel" value={d.category ?? ''} aria-label={`Kategorie von ${d.name}`}
                    onChange={(e) => change(d, { category: e.target.value }, `${d.name}: Kategorie ${e.target.value ? `„${e.target.value}“` : 'entfernt'}.`)}>
                    <option value="">– keine –</option>
                    {categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
                  </select>
                </td>
                <td>
                  <select className="role-sel" value={d.technician?.id ?? ''} aria-label={`Servicetechniker von ${d.name}`}
                    onChange={(e) => {
                      const id = e.target.value ? Number(e.target.value) : null
                      const name = technicians.find((t) => t.id === id)?.display_name
                      change(d, { technician_id: id }, id ? `${d.name} ist jetzt ${name} zugeordnet.` : `${d.name} ist keinem Servicetechniker mehr zugeordnet.`)
                    }}>
                    <option value="">– niemand –</option>
                    {technicians.map((t) => <option key={t.id} value={t.id}>{t.display_name}</option>)}
                  </select>
                </td>
                <td className={d.stale ? 'muted stale' : 'muted'}>{ago(d.minutes_since_last_message ?? d.minutes_since_last_seen)}</td>
                <td><div className="act">
                  {pendingDelete === d.device_id ? (
                    <>
                      <span className="q">Mit allen Messwerten löschen?</span>
                      <button type="button" className="btn-s danger-solid" onClick={() => remove(d)}>Löschen</button>
                      <button type="button" className="btn-s" onClick={() => setPendingDelete(null)}>Abbrechen</button>
                    </>
                  ) : (
                    <>
                      <button type="button" className="btn-s" onClick={() => { setMsg(null); setEditing(d) }}>Bearbeiten</button>
                      <button type="button" className="btn-s danger" onClick={() => setPendingDelete(d.device_id)}>Löschen</button>
                    </>
                  )}
                </div></td>
              </tr>
            ))}
            {devices && !shown.length && <tr><td colSpan={5} className="muted">{all.length ? 'Kein Gerät passt zur Suche.' : 'Noch keine Geräte.'}</td></tr>}
          </tbody>
        </table>
      </section>

      {editing && (
        <div className="overlay sheet" role="dialog" aria-modal="true" aria-label="Gerät bearbeiten"
          onClick={(e) => { if (e.target === e.currentTarget) setEditing(null) }}>
          <section className="card dialog">
            <h2>{editing.name} bearbeiten</h2>
            <DeviceForm device={editing} onCancel={() => setEditing(null)}
              onSubmit={async (data) => {
                await api.updateDevice(editing.device_id, data)
                setMsg(`${data.name || editing.device_id} gespeichert.`)
                setEditing(null)
                onChanged()
              }} />
          </section>
        </div>
      )}
    </>
  )
}

/* --- Kategorien (Admin) -------------------------------------------------------------------- */
export function CategoryAdmin({ onChanged }) {
  const [list, setList] = useState(null)
  const [name, setName] = useState('')
  const [renaming, setRenaming] = useState(null) // { id, name }
  const [pendingDelete, setPendingDelete] = useState(null)
  const [msg, setMsg] = useState(null)
  const [error, setError] = useState('')

  const load = () => api.categories().then(setList).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  async function run(action, text) {
    setError('')
    try {
      await action()
      setMsg(text)
      load()
      onChanged()
      return true
    } catch (err) {
      setError(err.message)
      return false
    }
  }

  async function create(e) {
    e.preventDefault()
    if (await run(() => api.createCategory(name), `Kategorie „${name.trim()}“ angelegt.`)) setName('')
  }
  async function rename(e) {
    e.preventDefault()
    if (await run(() => api.renameCategory(renaming.id, renaming.name), `Kategorie umbenannt in „${renaming.name.trim()}“.`)) setRenaming(null)
  }

  return (
    <>
      <p className="lead">Die Kategorien, aus denen bei jedem Gerät gewählt wird. Umbenennen ändert sie bei allen Geräten mit.</p>
      {msg && <p className="msg" role="status">{msg}</p>}
      {error && <p className="notice warn" role="alert">{error}</p>}
      <div className="adm-grid">
        <section className="card" aria-label="Neue Kategorie">
          <h2>Neue Kategorie</h2>
          <form className="form" onSubmit={create}>
            <label className="field"><span>Name</span>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} required maxLength={60} placeholder="z. B. Baustellenampel" /></label>
            <button className="btn" type="submit">Kategorie anlegen</button>
          </form>
        </section>

        <section className="card" aria-label="Alle Kategorien">
          <h2>Alle Kategorien</h2>
          {!list && !error && <p className="hint">Lade …</p>}
          {list && !list.length && <p className="hint">Noch keine Kategorien angelegt.</p>}
          <ul className="cat-list">
            {(list ?? []).map((c) => (
              <li key={c.id}>
                {renaming?.id === c.id ? (
                  <form className="cat-rename" onSubmit={rename}>
                    <input type="text" value={renaming.name} onChange={(e) => setRenaming({ ...renaming, name: e.target.value })}
                      required maxLength={60} aria-label={`Neuer Name für ${c.name}`} autoFocus />
                    <button className="btn btn-sm" type="submit">Speichern</button>
                    <button className="btn-s" type="button" onClick={() => setRenaming(null)}>Abbrechen</button>
                  </form>
                ) : (
                  <>
                    <span className="cat-name"><b>{c.name}</b>
                      <span className="meta">{c.device_count} {c.device_count === 1 ? 'Gerät' : 'Geräte'}</span></span>
                    <span className="act">
                      {pendingDelete === c.id ? (
                        <>
                          <span className="q">{c.device_count ? `${c.device_count} ${c.device_count === 1 ? 'Gerät verliert' : 'Geräte verlieren'} die Kategorie. Löschen?` : 'Wirklich löschen?'}</span>
                          <button type="button" className="btn-s danger-solid"
                            onClick={() => run(() => api.deleteCategory(c.id), `Kategorie „${c.name}“ gelöscht.`).then(() => setPendingDelete(null))}>Löschen</button>
                          <button type="button" className="btn-s" onClick={() => setPendingDelete(null)}>Abbrechen</button>
                        </>
                      ) : (
                        <>
                          <button type="button" className="btn-s" onClick={() => { setMsg(null); setRenaming({ id: c.id, name: c.name }) }}>Umbenennen</button>
                          <button type="button" className="btn-s danger" onClick={() => setPendingDelete(c.id)}>Löschen</button>
                        </>
                      )}
                    </span>
                  </>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  )
}
