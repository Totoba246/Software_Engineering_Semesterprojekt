/*
 * PAGE "Nutzerverwaltung" (Admin only), layout from the GUI draft.
 * Create accounts, change roles, lock/unlock, reset passwords, delete.
 *
 * There's no e-mail sending: a new account gets a START PASSWORD that is shown
 * here ONCE. Pass it on to the person; they must choose an own password at the
 * first login. The server enforces all rules (e.g. you can't lock yourself out).
 */
import { useEffect, useMemo, useState } from 'react'
import { api, ROLES } from '../api.js'
import { dateTime } from '../format.js'

const ROLE_ORDER = Object.keys(ROLES)
const EMPTY = { display_name: '', username: '', email: '', role: 'techniker', password: '' }

export default function UserAdmin({ me }) {
  const [users, setUsers] = useState(null)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState(null) // { text, password? }
  const [form, setForm] = useState(EMPTY)
  const [formError, setFormError] = useState('')
  const [query, setQuery] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [pendingDelete, setPendingDelete] = useState(null)

  const load = () => api.users().then(setUsers).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  async function create(e) {
    e.preventDefault()
    setFormError('')
    try {
      const u = await api.createUser({ ...form, username: form.username.trim().toLowerCase() })
      setMsg({ text: `${u.display_name} wurde als ${ROLES[u.role]} angelegt. Benutzername: ${u.username}`, password: u.start_password })
      setForm({ ...EMPTY, role: form.role })
      load()
    } catch (err) {
      setFormError(err.message)
    }
  }

  async function act(u, change, text) {
    setError('')
    try {
      const updated = await api.updateUser(u.id, change)
      setMsg({ text, password: updated.start_password })
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  async function remove(u) {
    setError('')
    try {
      await api.deleteUser(u.id)
      setMsg({ text: `${u.display_name} wurde gelöscht.` + (u.device_count ? ` ${u.device_count} Gerät(e) sind jetzt keinem Servicetechniker zugeordnet.` : '') })
      setPendingDelete(null)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (users ?? [])
      .filter((u) => (!roleFilter || u.role === roleFilter) &&
        (!q || [u.display_name, u.username, u.email].some((v) => v?.toLowerCase().includes(q))))
      .sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role) || a.display_name.localeCompare(b.display_name, 'de'))
  }, [users, query, roleFilter])

  const all = users ?? []
  const stats = [
    [all.length, 'Nutzer gesamt'], [all.filter((u) => u.active).length, 'aktiv'],
    [all.filter((u) => !u.active).length, 'gesperrt'], [all.filter((u) => u.role === 'techniker').length, 'Servicetechniker'],
  ]

  return (
    <div className="scroll">
      <div className="page">
        <div className="d-head">
          <h1>Nutzerverwaltung</h1>
          <p>Konten anlegen, Rollen ändern, sperren und löschen. Gesperrte Nutzer können sich nicht mehr anmelden.</p>
        </div>
        {msg && (
          <div className="msg" role="status">
            {msg.text}
            {msg.password && (
              <p>Start-Passwort (wird nur jetzt angezeigt, bitte weitergeben): <code className="pw">{msg.password}</code></p>
            )}
            <button type="button" className="reset" onClick={() => setMsg(null)}>Ausblenden</button>
          </div>
        )}
        {error && <p className="hint warn" role="alert">{error}</p>}
        <div className="stats">{stats.map(([n, l]) => <div className="stat" key={l}><b>{n}</b><span>{l}</span></div>)}</div>

        <div className="adm-grid">
          <section className="card" aria-label="Neuen Nutzer anlegen">
            <h2>Neuen Nutzer anlegen</h2>
            <form className="form" onSubmit={create}>
              <label className="field"><span>Name</span>
                <input type="text" value={form.display_name} onChange={set('display_name')} placeholder="Vorname Nachname" required maxLength={100} /></label>
              <label className="field"><span>Benutzername (zum Anmelden)</span>
                <input type="text" value={form.username} onChange={set('username')} placeholder="z. B. e.aydin" required maxLength={50} /></label>
              <label className="field"><span>E-Mail (optional)</span>
                <input type="email" value={form.email} onChange={set('email')} placeholder="name@betreiber.de" maxLength={200} /></label>
              <label className="field"><span>Rolle</span>
                <select value={form.role} onChange={set('role')}>
                  {Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select></label>
              <label className="field"><span>Start-Passwort (leer = automatisch erzeugen)</span>
                <input type="text" value={form.password} onChange={set('password')} autoComplete="off" maxLength={200} /></label>
              {formError && <p className="hint warn" role="alert">{formError}</p>}
              <button className="btn" type="submit">Nutzer anlegen</button>
            </form>
          </section>

          <section className="card" aria-label="Alle Nutzer">
            <div className="card-head">
              <h2>Alle Nutzer</h2>
              <div className="tbl-filters">
                <input type="search" placeholder="Name oder Benutzername" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Nutzer suchen" />
                <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} aria-label="Nach Rolle filtern">
                  <option value="">Alle Rollen</option>
                  {Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
            </div>
            {!users && !error && <p className="hint">Lade …</p>}
            <table className="users">
              <thead><tr><th>Nutzer</th><th>Rolle</th><th>Status</th><th>Zuletzt angemeldet</th><th><span className="sr">Aktionen</span></th></tr></thead>
              <tbody>
                {shown.map((u) => {
                  const self = u.id === me.id
                  return (
                    <tr key={u.id} className={u.active ? '' : 'locked'}>
                      <td><div className="u"><div>
                        <span><b>{u.display_name}</b>{self && <span className="you">Sie</span>}</span>
                        <span className="meta">{u.username}{u.email ? ` · ${u.email}` : ''}</span>
                      </div></div></td>
                      <td>
                        {self ? <span className={`role r-${u.role}`}>{ROLES[u.role]}</span> : (
                          <select className="role-sel" value={u.role} aria-label={`Rolle von ${u.display_name}`}
                            onChange={(e) => act(u, { role: e.target.value }, `${u.display_name} ist jetzt ${ROLES[e.target.value]}.`)}>
                            {Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                          </select>
                        )}
                        {u.role === 'techniker' && <span className="meta" style={{ display: 'block' }}>{u.device_count} {u.device_count === 1 ? 'Gerät' : 'Geräte'}</span>}
                      </td>
                      <td>
                        <span className={`st ${u.active ? 's-ok' : 's-krit'}`}><i className="dot" />{u.active ? 'Aktiv' : 'Gesperrt'}</span>
                        {u.must_change_password && u.active && <span className="meta" style={{ display: 'block' }}>Start-Passwort</span>}
                      </td>
                      <td className="muted">{u.last_login_at ? dateTime(u.last_login_at) : 'noch nie'}</td>
                      <td><div className="act">
                        {self ? <span className="hint">eigenes Konto</span>
                          : pendingDelete === u.id ? (
                            <>
                              <span className="q">Wirklich löschen?</span>
                              <button type="button" className="btn-s danger-solid" onClick={() => remove(u)}>Löschen</button>
                              <button type="button" className="btn-s" onClick={() => setPendingDelete(null)}>Abbrechen</button>
                            </>
                          ) : (
                            <>
                              <button type="button" className="btn-s" onClick={() => act(u, { active: !u.active }, `${u.display_name} wurde ${u.active ? 'gesperrt' : 'entsperrt'}.`)}>
                                {u.active ? 'Sperren' : 'Entsperren'}</button>
                              <button type="button" className="btn-s" onClick={() => act(u, { reset_password: true }, `Neues Start-Passwort für ${u.display_name}.`)}>
                                Passwort zurücksetzen</button>
                              <button type="button" className="btn-s danger" onClick={() => setPendingDelete(u.id)}>Löschen</button>
                            </>
                          )}
                      </div></td>
                    </tr>
                  )
                })}
                {users && !shown.length && <tr><td colSpan={5} className="muted">Kein Nutzer passt zur Suche.</td></tr>}
              </tbody>
            </table>
          </section>
        </div>
      </div>
    </div>
  )
}
