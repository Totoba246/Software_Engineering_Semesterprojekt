/*
 * Date helpers for the calendar and the appointments (everything in the
 * browser's time zone). Used by pages/Calendar.jsx, pages/DeviceDetail.jsx
 * and components/AppointmentForm.jsx.
 */

export const DAY = 24 * 3600e3
export const WEEKDAYS_LONG = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag']
export const MONTHS = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

export const p2 = (n) => String(n).padStart(2, '0')

// "2026-11-17" (the key of a calendar day)
export const dayKey = (date) => {
  const d = new Date(date)
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`
}
export const parseKey = (key) => {
  const [y, m, d] = key.split('-').map(Number)
  return new Date(y, m - 1, d)
}
export const addDays = (date, n) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + n)
export const weekStart = (date) => addDays(date, -((date.getDay() + 6) % 7)) // the Monday of that week
// "08:30"
export const hhmm = (date) => {
  const d = new Date(date)
  return `${p2(d.getHours())}:${p2(d.getMinutes())}`
}
// "Di 17.11."
export const shortDay = (date) => {
  const d = new Date(date)
  return `${WEEKDAYS_LONG[d.getDay()].slice(0, 2)} ${d.getDate()}.${p2(d.getMonth() + 1)}.`
}

// The date the device should be replaced by: when it becomes critical (or empty).
export const dueAt = (d) => d.estimated_critical_at ?? d.estimated_empty_at
// Suggested replacement day: one day before it becomes critical, at the earliest today.
export function suggestedDay(d) {
  const due = dueAt(d)
  const today = new Date()
  if (!due) return dayKey(today)
  return dayKey(Math.max(today.getTime(), new Date(due).getTime() - DAY))
}
