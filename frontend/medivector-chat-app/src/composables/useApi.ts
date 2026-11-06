let demoAutoConnect = false

export function isDemoAutoConnect () {
  return demoAutoConnect
}

// Discover explicit server-side demo mode without exposing or storing a demo Token.
export async function initializeConnection () {
  demoAutoConnect = false
  try {
    const response = await fetch('/api/session', { cache: 'no-store', signal: AbortSignal.timeout(3000) })
    if (!response.ok) {
      return
    }
    const session = await response.json()
    demoAutoConnect = session.workspace === 'institutional' && session.connection_mode === 'demo_auto'
  } catch {
    // Normal authenticated mode remains available when discovery is denied or unavailable.
  }
}

export async function api<T> (path: string, options: RequestInit = {}): Promise<T> {
  const requestOptions: RequestInit = { ...options }
  const headers = new Headers(options.headers)
  const token = sessionStorage.getItem('apiToken')
  if (demoAutoConnect) {
    headers.delete('Authorization')
  } else if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  requestOptions.headers = headers
  const response = await fetch(path, requestOptions)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(body.error || `HTTP ${response.status}`)
  }
  return body as T
}

// Binary source reads retain authorization and never put credentials into a URL.
export async function apiBlob (path: string): Promise<Blob> {
  const headers = new Headers()
  const token = sessionStorage.getItem('apiToken')
  if (!demoAutoConnect && token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const response = await fetch(path, { headers, cache: 'no-store' })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.error || `HTTP ${response.status}`)
  }
  return response.blob()
}
