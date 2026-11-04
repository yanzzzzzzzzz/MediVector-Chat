import assert from 'node:assert/strict'
import { afterEach, beforeEach, mock, test } from 'node:test'
import { api } from '../src/composables/useApi.ts'

const storageDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage')
let token: string | null = null

beforeEach(() => {
  token = null
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: { getItem: () => token },
  })
})

afterEach(() => {
  mock.restoreAll()
  if (storageDescriptor) {
    Object.defineProperty(globalThis, 'sessionStorage', storageDescriptor)
  } else {
    Reflect.deleteProperty(globalThis, 'sessionStorage')
  }
})

test('adds the session Token and preserves caller headers without mutating them', async () => {
  token = 'test-token'
  let sent: RequestInit | undefined
  mock.method(globalThis, 'fetch', async (_path: string, options: RequestInit) => {
    sent = options
    return Response.json({ documents: [] })
  })
  const headers = new Headers({ 'X-Request-Id': 'request-1' })
  assert.deepEqual(await api('/api/documents', { headers }), { documents: [] })
  const actual = new Headers(sent?.headers)
  assert.equal(actual.get('Authorization'), 'Bearer test-token')
  assert.equal(actual.get('X-Request-Id'), 'request-1')
  assert.equal(actual.get('Content-Type'), 'application/json')
  assert.equal(headers.get('Authorization'), null)
})

test('local mode sends no authorization header when the Token is absent', async () => {
  mock.method(globalThis, 'fetch', async (_path: string, options: RequestInit) => {
    assert.equal(new Headers(options.headers).get('Authorization'), null)
    return Response.json({ ok: true })
  })
  assert.deepEqual(await api('/api/documents'), { ok: true })
})

test('multipart upload keeps its body and lets the browser supply the boundary', async () => {
  token = 'test-token'
  const body = new FormData()
  body.append('file', new Blob(['test']), 'test.txt')
  mock.method(globalThis, 'fetch', async (_path: string, options: RequestInit) => {
    const headers = new Headers(options.headers)
    assert.equal(options.body, body)
    assert.equal(headers.get('Content-Type'), null)
    assert.equal(headers.get('Authorization'), 'Bearer test-token')
    assert.equal(headers.get('X-Request-Id'), 'upload-1')
    return Response.json({ inserted: [] })
  })
  await api('/api/documents', { method: 'POST', body, headers: { 'X-Request-Id': 'upload-1' } })
})

test('returns API authorization errors to the user', async () => {
  mock.method(globalThis, 'fetch', async () => Response.json({ error: 'API authorization required' }, { status: 401 }))
  await assert.rejects(api('/api/documents'), /API authorization required/)
})

test('reports HTTP status when the server returns a non-JSON error', async () => {
  mock.method(globalThis, 'fetch', async () => new Response('gateway unavailable', { status: 502 }))
  await assert.rejects(api('/api/documents'), /HTTP 502/)
})
