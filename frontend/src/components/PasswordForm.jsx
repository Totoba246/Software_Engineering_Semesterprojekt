/*
 * CHANGE OWN PASSWORD. Used twice:
 *  - forced after the first login with a start password (forced = true)
 *  - voluntarily via "Passwort ändern" in the header
 */
import { useState } from 'react'
import { api } from '../api.js'

export default function PasswordForm({ forced = false, onDone, onCancel }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (next !== repeat) return setError('Die beiden neuen Passwörter stimmen nicht überein.')
    if (next.length < 8) return setError('Das neue Passwort muss mindestens 8 Zeichen lang sein.')
    setBusy(true)
    setError('')
    try {
      await api.changePassword(current, next)
      onDone?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      {forced && <p className="hint">Sie haben ein Start-Passwort bekommen. Bitte legen Sie jetzt ein eigenes Passwort fest.</p>}
      <label className="field">
        <span>{forced ? 'Start-Passwort' : 'Bisheriges Passwort'}</span>
        <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
      </label>
      <label className="field">
        <span>Neues Passwort (mind. 8 Zeichen)</span>
        <input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required />
      </label>
      <label className="field">
        <span>Neues Passwort wiederholen</span>
        <input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} required />
      </label>
      {error && <p className="hint warn" role="alert">{error}</p>}
      <div className="row-btns">
        <button className="btn" type="submit" disabled={busy}>Passwort speichern</button>
        {onCancel && <button className="btn-s" type="button" onClick={onCancel}>Abbrechen</button>}
      </div>
    </form>
  )
}
