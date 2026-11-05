// Thin wrapper around the BatteryWatch REST API (see backend/batterywatch/api/main.py).

async function get(path) {
  const res = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch {
      /* body was not JSON */
    }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return res.json()
}

export const api = {
  devices: () => get('/api/devices'),
  device: (id) => get(`/api/devices/${encodeURIComponent(id)}`),
  history: (id, hours) => get(`/api/devices/${encodeURIComponent(id)}/history?hours=${hours}`),
  messages: (id, limit = 20) => get(`/api/devices/${encodeURIComponent(id)}/messages?limit=${limit}`),
  statusRules: () => get('/api/status-rules'),
}
