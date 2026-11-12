/*
 * ALL CONVERSATIONS WITH THE BACKEND go through this file.
 *
 * The page asks for data with fetch('/api/...'). Where does that request go?
 *   - in Docker / on the server: the same address the page came from
 *     (http://<host>:20800/api/...), and nginx forwards it to the api container
 *     (see frontend/nginx.conf)
 *   - during development (npm run dev): Vite forwards it to localhost:8000
 *     (see vite.config.js)
 * The answers are JSON; their exact shape is documented at /docs of the API.
 *
 * LOGIN: the browser automatically sends the login cookie ("bw_session") with
 * every request. If the server answers 401 ("not logged in", e.g. the login
 * expired), we announce it with the event "bw:unauthorized"; App.jsx then
 * shows the login page.
 */

async function request(method, path, body) {
  const options = { method, headers: { Accept: 'application/json' }, credentials: 'same-origin' }
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }
  const res = await fetch(path, options)
  if (res.status === 401 && path !== '/api/auth/login') {
    window.dispatchEvent(new Event('bw:unauthorized'))
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      // FastAPI: either a text, or a list of field errors (422)
      detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join('; ') : data.detail || detail
    } catch {
      /* body was not JSON */
    }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return res.status === 204 ? null : res.json()
}

const get = (path) => request('GET', path)
const enc = encodeURIComponent

export const api = {
  // login
  me: () => get('/api/auth/me'),
  login: (username, password) => request('POST', '/api/auth/login', { username, password }),
  logout: () => request('POST', '/api/auth/logout'),
  changePassword: (current_password, new_password) =>
    request('POST', '/api/auth/password', { current_password, new_password }),

  // devices (Firmenchef/Mitarbeiter: all, Servicetechniker: only assigned)
  devices: () => get('/api/devices'),
  device: (id) => get(`/api/devices/${enc(id)}`),
  history: (id, hours) => get(`/api/devices/${enc(id)}/history?hours=${hours}`),
  messages: (id, limit = 20) => get(`/api/devices/${enc(id)}/messages?limit=${limit}`),
  statusRules: () => get('/api/status-rules'),
  // master data (Firmenchef/Mitarbeiter)
  technicians: () => get('/api/technicians'),
  createDevice: (data) => request('POST', '/api/devices', data),
  updateDevice: (id, data) => request('PATCH', `/api/devices/${enc(id)}`, data),
  deleteDevice: (id) => request('DELETE', `/api/devices/${enc(id)}`),

  // user management (admin)
  users: () => get('/api/users'),
  createUser: (data) => request('POST', '/api/users', data),
  updateUser: (id, data) => request('PATCH', `/api/users/${id}`, data),
  deleteUser: (id) => request('DELETE', `/api/users/${id}`),
}

export const ROLES = { admin: 'Admin', chef: 'Firmenchef', mitarbeiter: 'Mitarbeiter', techniker: 'Servicetechniker' }
export const isManagement = (user) => user?.role === 'chef' || user?.role === 'mitarbeiter'
