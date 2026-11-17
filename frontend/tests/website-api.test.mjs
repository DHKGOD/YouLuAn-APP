import test from 'node:test'
import assert from 'node:assert/strict'
import { Capacitor } from '@capacitor/core'
import { defaultServer, getServer, isIOSWebsite, websiteApiPath } from '../src/api.js'

const key = '/website-test-' + 'x'.repeat(40)
globalThis.location = { origin: 'https://website.example', protocol: 'https:', port: '' }
globalThis.document = { querySelector: () => ({ content: key }) }
globalThis.localStorage = { getItem: () => 'https://old-server.invalid' }

test('website keeps the protected path and ignores a stale saved server', () => {
  Capacitor.isNativePlatform = () => false
  assert.equal(websiteApiPath(), key)
  assert.equal(defaultServer(), 'https://website.example' + key)
  assert.equal(getServer(), 'https://website.example' + key)
})

test('native Android retains its own configuration and no embedded website address', () => {
  Capacitor.isNativePlatform = () => true
  assert.equal(websiteApiPath(), '')
  assert.equal(defaultServer(), '')
  assert.equal(getServer(), 'https://old-server.invalid')
})

test('iPhone Safari and desktop-mode iPad are websites, Android is unaffected', () => {
  Capacitor.isNativePlatform = () => false
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { userAgent: 'iPhone', platform: 'iPhone' } })
  assert.equal(isIOSWebsite(), true)
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { userAgent: 'Macintosh', platform: 'MacIntel', maxTouchPoints: 5 } })
  assert.equal(isIOSWebsite(), true)
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { userAgent: 'Android', platform: 'Linux' } })
  assert.equal(isIOSWebsite(), false)
})
