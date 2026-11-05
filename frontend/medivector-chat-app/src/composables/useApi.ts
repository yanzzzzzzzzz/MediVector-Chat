export async function api<T> (path: string, options: RequestInit = {}): Promise<T> {
  const requestOptions: RequestInit = { ...options }
  const headers = new Headers(options.headers)
  const token = sessionStorage.getItem('apiToken')
  if (token) {
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
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const response = await fetch(path, { headers, cache: 'no-store' })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.error || `HTTP ${response.status}`)
  }
  return response.blob()
}
