import assert from 'node:assert/strict'
import { afterEach, beforeEach, mock, test } from 'node:test'
import { api, apiBlob, initializeConnection, isDemoAutoConnect } from '../src/composables/useApi.ts'

const storageDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage')
beforeEach(() => {
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: { getItem: () => 'stale-personal-token' } })
})
afterEach(() => {
  mock.restoreAll()
  if (storageDescriptor) {
    Object.defineProperty(globalThis, 'sessionStorage', storageDescriptor)
  } else {
    Reflect.deleteProperty(globalThis, 'sessionStorage')
  }
})

test('explicit demo discovery needs no credential and omits stale Tokens from JSON and PDF reads', async () => {
  mock.method(globalThis, 'fetch', async (_path: string, options: RequestInit = {}) => {
    assert.equal(new Headers(options.headers).get('Authorization'), null)
    return Response.json({ workspace: 'institutional', connection_mode: 'demo_auto' })
  })
  await initializeConnection()
  assert.equal(isDemoAutoConnect(), true)
  await api('/api/knowledge/catalog', { headers: { Authorization: 'Bearer stale-explicit-token' } })
  await apiBlob('/api/knowledge/versions/demo/attachment')
})

test('normal authenticated deployment retains stored credentials when anonymous discovery is denied', async () => {
  mock.method(globalThis, 'fetch', async () => Response.json({ error: 'auth required' }, { status: 401 }))
  await initializeConnection()
  assert.equal(isDemoAutoConnect(), false)
  mock.method(globalThis, 'fetch', async (_path: string, options: RequestInit = {}) => {
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer stale-personal-token')
    return Response.json({ ok: true })
  })
  await api('/api/session')
})

test('network failure or an ordinary local workspace never enables demo auto-connection', async () => {
  mock.method(globalThis, 'fetch', async () => {
    throw new Error('offline')
  })
  await initializeConnection()
  assert.equal(isDemoAutoConnect(), false)
  mock.method(globalThis, 'fetch', async () => Response.json({ workspace: 'legacy' }))
  await initializeConnection()
  assert.equal(isDemoAutoConnect(), false)
})
