const API_BASE = import.meta.env.VITE_API_BASE || '/api'

function tenantId(): string {
  return import.meta.env.VITE_TENANT_ID || '00000000-0000-0000-0000-000000000001'
}

function userId(): string {
  return import.meta.env.VITE_USER_ID || 'alice'
}

function headers(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'X-Tenant-Id': tenantId(),
    'X-User-Id': userId(),
  }
}

export async function apiGet(path: string) {
  const res = await fetch(`${API_BASE}${path}`, { headers: headers() })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export async function apiPost(path: string, body?: unknown) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: headers(),
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export async function apiDelete(path: string) {
  const res = await fetch(`${API_BASE}${path}`, { method: 'DELETE', headers: headers() })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}
