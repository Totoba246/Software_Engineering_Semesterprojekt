import { useEffect, useMemo, useRef } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { Link } from 'react-router-dom'
import { pct } from '../format.js'

const GERMANY = [[47.3, 5.9], [55.1, 15.0]]

// Fit the map to the devices once (and again when the set of devices changes),
// but not on every poll, so the user's zoom is kept.
function FitToDevices({ devices }) {
  const map = useMap()
  const key = devices.map((d) => d.device_id).sort().join('|')
  const fitted = useRef(null)
  useEffect(() => {
    if (!devices.length || fitted.current === key) return
    fitted.current = key
    const pts = devices.map((d) => [d.position.latitude, d.position.longitude])
    map.fitBounds(pts, { padding: [50, 50], maxZoom: 14 })
  }, [key, devices, map])
  return null
}

export default function DeviceMap({ devices, selectedId, onHover, interactive = true }) {
  const located = useMemo(() => devices.filter((d) => d.position), [devices])
  return (
    <MapContainer
      className="maphost"
      bounds={GERMANY}
      scrollWheelZoom={interactive}
      dragging={interactive}
      attributionControl
    >
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>-Mitwirkende'
        maxZoom={19}
      />
      <FitToDevices devices={located} />
      {located.map((d) => (
        <CircleMarker
          key={d.device_id}
          center={[d.position.latitude, d.position.longitude]}
          radius={d.device_id === selectedId ? 11 : 8}
          pathOptions={{ className: `mk s-${d.status} mk-${d.status}${d.device_id === selectedId ? ' sel' : ''}` }}
          eventHandlers={{
            mouseover: () => onHover?.(d.device_id),
            mouseout: () => onHover?.(null),
          }}
        >
          <Tooltip direction="top" offset={[0, -8]}>{d.name}: {pct(d.soc_percent)}</Tooltip>
          {interactive && (
            <Popup>
              <Link to={`/geraete/${encodeURIComponent(d.device_id)}`}>{d.name}</Link>
              <br />Akku {pct(d.soc_percent)}
            </Popup>
          )}
        </CircleMarker>
      ))}
    </MapContainer>
  )
}
