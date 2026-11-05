import { pct } from '../format.js'

export function BatteryIcon({ device }) {
  const fill = Math.max(device.soc_percent ?? 0, 3)
  return (
    <span className={`batt s-${device.status}`} aria-hidden="true">
      <span className="batt-fill" style={{ width: `${fill}%` }} />
    </span>
  )
}

export function BatteryLevel({ device }) {
  return (
    <span className={`lvl s-${device.status}`}>
      <BatteryIcon device={device} />
      <span className="pct">{pct(device.soc_percent)}</span>
    </span>
  )
}

export function Legend({ rules }) {
  const crit = rules?.critical_below_percent ?? 20
  const low = rules?.low_below_percent ?? 50
  return (
    <div className="legend" aria-label="Legende">
      <span className="s-krit"><i className="dot" />unter {crit} %</span>
      <span className="s-niedrig"><i className="dot" />{crit} bis {low - 1} %</span>
      <span className="s-ok"><i className="dot" />ab {low} %</span>
    </div>
  )
}
