export async function api<T> (path: string, options: RequestInit = {}): Promise<T> {
  const requestOptions: RequestInit = { ...options }
  if (!(options.body instanceof FormData)) {
    requestOptions.headers = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> | undefined),
    }
  }
  const response = await fetch(path, requestOptions)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(body.error || `HTTP ${response.status}`)
  }
  return body as T
}
