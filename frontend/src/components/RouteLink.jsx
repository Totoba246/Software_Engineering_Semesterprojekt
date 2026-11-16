/*
 * "ROUTE" BUTTON: opens Google Maps with the device as destination.
 *
 * On a phone the link opens the Google Maps app (if installed) and starts
 * from the current location; on a computer it opens maps.google.com in a new tab.
 * No API key and no Google code on our page - it is just a link:
 *   https://www.google.com/maps/dir/?api=1&destination=<lat>,<lon>
 *
 * The destination is the device's position from the API (average of its GPS
 * fixes of the last days). A device without GPS (e.g. node 101 right now) has
 * no exact destination: if a place name is stored ("Ort"), we offer a search
 * for that place instead and say so; otherwise there is no button.
 *
 * Used in: device detail page, calendar entries, device list, map popup.
 */

export function routeUrl(device) {
  const p = device?.position
  if (!p) return null
  return `https://www.google.com/maps/dir/?api=1&destination=${p.latitude.toFixed(6)},${p.longitude.toFixed(6)}`
}

export function placeUrl(device) {
  if (!device?.location) return null
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(device.location)}`
}

// small "navigation arrow" icon (inline SVG, takes the text colour)
export function RouteIcon({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M13.9 1.4 2 6.5c-.5.2-.4.9.1 1l4.6 1 1 4.6c.1.5.8.6 1 .1l5.1-11.9c.2-.5-.3-1-.9-.9Z" />
    </svg>
  )
}

/*
 * variant: "btn"   big primary button (detail page)
 *          "small" small outlined button (calendar entries, popups)
 *          "icon"  round icon-only button (device list rows)
 */
export default function RouteLink({ device, variant = 'small', className = '' }) {
  const exact = routeUrl(device)
  const href = exact ?? placeUrl(device)
  if (!href) return null
  const name = device.name ?? device.device_id
  const label = exact ? 'Route' : 'Ort suchen'
  const title = exact
    ? `Route zu ${name} in Google Maps öffnen`
    : `${name} hat kein GPS – den Ort „${device.location}“ in Google Maps suchen`
  const cls = { btn: 'btn route', small: 'btn-s route', icon: 'route-ic' }[variant]
  return (
    <a className={`${cls} ${className}`.trim()} href={href} target="_blank" rel="noopener noreferrer"
      title={title} aria-label={variant === 'icon' ? title : undefined}>
      <RouteIcon size={variant === 'btn' ? 16 : 14} />
      {variant !== 'icon' && <span>{variant === 'btn' && exact ? 'Route starten' : label}</span>}
    </a>
  )
}
