import test from 'node:test'
import assert from 'node:assert/strict'
import { Capacitor } from '@capacitor/core'
import { api, defaultServer, getServer, normalize, setServer } from '../src/api.js'

const saved = new Map()
globalThis.localStorage = { getItem: key => saved.get(key) ?? null, setItem: (key, value) => saved.set(key, value) }
Capacitor.isNativePlatform = () => true

test('fresh native install has no default server and makes no API request', async () => {
  saved.clear()
  assert.equal(defaultServer(), '')
  assert.equal(getServer(), '')
  let requests = 0
  globalThis.fetch = async () => { requests++; throw new Error('must not connect') }
  await assert.rejects(api('/api/health'), /尚未設定伺服器位址/)
  assert.equal(requests, 0)
})

test('owner-provided HTTPS path is preserved exactly and persists locally', async () => {
  const address = 'https://owner-server.example.invalid/CaseSensitive_Code-123'
  assert.equal(normalize(address + '/'), address)
  assert.equal(setServer(address), address)
  assert.equal(getServer(), address)
  let actual
  globalThis.fetch = async url => { actual = url; return { ok: true, json: async () => ({ status: 'ok' }) } }
  await api('/api/health')
  assert.equal(actual, address + '/api/health')
})
