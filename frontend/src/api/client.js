const BASE = import.meta.env.VITE_API_URL || '/api/v1'
const TENANT = 'demo'

const headers = () => ({
  'Content-Type': 'application/json',
  'X-Tenant-Id': TENANT,
})

async function req(path, init = {}) {
  const url = path.startsWith('http') ? path : `${BASE}${path}`
  const res = await fetch(url, { ...init, headers: { ...headers(), ...(init.headers || {}) } })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  listZones: () => req('/zones'),
  createZone: (name, geometry) =>
    req('/zones', {
      method: 'POST',
      body: JSON.stringify({ name, geometry, tenant_id: TENANT }),
    }),
  deleteZone: (id) => req(`/zones/${id}`, { method: 'DELETE' }),
  indices: (id) => req(`/indices/${id}`),
  risk: (id) => req(`/risk/${id}`),
  summary: () => req('/summary'),
  health: () => fetch(`${BASE.replace(/\/api\/v1$/, '')}/health`).then(r => r.ok),
}
