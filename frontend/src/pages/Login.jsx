/*
 * LOGIN PAGE (F06). Shown whenever nobody is logged in.
 * Sends username + password to POST /api/auth/login; the server answers with
 * the user and sets the login cookie. Accounts are created by an admin
 * (Nutzerverwaltung); the very first admin by `python start.py`.
 */
import { useState } from 'react'
import { api } from '../api.js'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      onLogin(await api.login(username.trim(), password))
    } catch (err) {
      setError(err.message)
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="center-page">
      <form className="card login" onSubmit={submit}>
        <div className="brand login-brand">
          <span className="lamp" aria-hidden="true"><i /><i /><i /></span>BatteryWatch
        </div>
        <label className="field">
          <span>Benutzername</span>
          <input type="text" autoComplete="username" autoFocus value={username}
            onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label className="field">
          <span>Passwort</span>
          <input type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="hint warn" role="alert">{error}</p>}
        <button className="btn" type="submit" disabled={busy}>{busy ? 'Anmelden …' : 'Anmelden'}</button>
        <p className="hint">Passwort vergessen? Die Nutzerverwaltung (Admin) kann es zurücksetzen.</p>
      </form>
    </div>
  )
}
