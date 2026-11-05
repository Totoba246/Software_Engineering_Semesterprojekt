/*
 * ALL CONVERSATIONS WITH THE BACKEND go through this file.
 *
 * The page asks for data with fetch('/api/...'). Where does that request go?
 *   - on the server (Docker): the same address the page came from
 *     (http://<server>:20800/api/...), and nginx forwards it to the api container
 *     (see frontend/nginx.conf)
 *   - during development (npm run dev): Vite forwards it to localhost:8000
 *     (see vite.config.js)
 * The answers are JSON; their exact shape is documented at /docs of the API
 * and in backend/batterywatch/api/main.py.
 */

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
