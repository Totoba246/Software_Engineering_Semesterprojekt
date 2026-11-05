// Client-side helpers mirroring backend/batterywatch/battery.py (for chart bands only;
// the authoritative status always comes from the API).

export function socFromVoltage(volts, curve) {
  if (volts == null || !curve?.length) return null
  if (volts <= curve[0][0]) return curve[0][1]
  const last = curve[curve.length - 1]
  if (volts >= last[0]) return last[1]
  for (let i = 0; i < curve.length - 1; i++) {
    const [v0, p0] = curve[i]
    const [v1, p1] = curve[i + 1]
    if (volts >= v0 && volts <= v1) return p0 + ((volts - v0) * (p1 - p0)) / (v1 - v0)
  }
  return null
}
