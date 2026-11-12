/*
 * HELPERS THAT TURN NUMBERS AND TIMES INTO GERMAN TEXT
 *   11.276        -> "11,3"
 *   35.2          -> "35 %"
 *   12 (minutes)  -> "vor 12 Min."
 *   a timestamp   -> "Do., 05.11.2026, 09:37"  (in the browser's time zone)
 */

const nf = (digits) =>
  new Intl.NumberFormat('de-DE', { minimumFractionDigits: digits, maximumFractionDigits: digits })

export const num = (value, digits = 1) => (value == null ? '–' : nf(digits).format(value))

export const pct = (value) => (value == null ? '–' : `${Math.round(value)} %`)

export function ago(minutes) {
  if (minutes == null) return 'nie'
  const m = Math.round(minutes)
  if (m < 1) return 'gerade eben'
  if (m < 60) return `vor ${m} Min.`
  const h = Math.floor(m / 60)
  if (h < 24) return `vor ${h} Std.`
  const d = Math.floor(h / 24)
  return d === 1 ? 'vor 1 Tag' : `vor ${d} Tagen`
}

const dtf = new Intl.DateTimeFormat('de-DE', {
  weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
})
export const dateTime = (iso) => (iso ? dtf.format(new Date(iso)) : '–')

const tf = new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit' })
export const time = (d) => (d ? tf.format(d) : '–')

export const STATUS_LABEL = { krit: 'Kritisch', niedrig: 'Niedrig', ok: 'Gut', unbekannt: 'Unbekannt' }
export const STATUS_ORDER = { krit: 0, niedrig: 1, ok: 2, unbekannt: 3 }
