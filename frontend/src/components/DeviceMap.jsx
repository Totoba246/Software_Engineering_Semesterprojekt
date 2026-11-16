/*
 * THE MAP (library "Leaflet"). Shows every device that has a GPS position as a
 * colored dot (green / yellow / red = battery status).
 * The map pictures ("tiles") are loaded by the BROWSER directly from
 * tile.openstreetmap.org - so the map background needs internet access.
 * Devices without GPS (e.g. node 101 right now: lat/lon = null) don't appear on the map.
 */

import { useEffect, useMemo, useRef } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { Link } from 'react-router-dom'
import { pct } from '../format.js'
import RouteLink from './RouteLink.jsx'

const GERMANY = [[47.3, 5.9], [55.1, 15.0]]

// Fit the map to the devices once (and again when the set of devices changes),
// but not on every poll, so the user's zoom is kept.
// On a phone the map can be hidden (list/map switch): Leaflet then has size 0 and
// can't fit anything. So we watch the map's size, tell Leaflet about changes
// (invalidateSize) and do the fit as soon as the map is really visible.
function FitToDevices({ devices }) {
  const map = useMap()
  const key = devices.map((d) => d.device_id).sort().join('|')
  const fitted = useRef(null)
  const latest = useRef({ key, devices })
  latest.current = { key, devices }

  const fitIfNeeded = () => {
    const { key: k, devices: list } = latest.current
    if (!list.length || fitted.current === k || map.getSize().x === 0) return
    fitted.current = k
    map.fitBounds(list.map((d) => [d.position.latitude, d.position.longitude]), { padding: [50, 50], maxZoom: 14 })
  }

  useEffect(fitIfNeeded, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => {
      map.invalidateSize()
      fitIfNeeded()
    })
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [map]) // eslint-disable-line react-hooks/exhaustive-deps
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
              <br />Akku {pct(d.soc_percent)}{d.location ? ` · ${d.location}` : ''}
              <div className="popup-actions"><RouteLink device={d} /></div>
            </Popup>
          )}
        </CircleMarker>
      ))}
    </MapContainer>
  )
}
