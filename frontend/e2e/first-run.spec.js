import { test, expect } from '@playwright/test'

test('公開APK首次設定：沒有預設位址，須向管理者取得後才連線', async ({ page }) => {
  const requests = []
  await page.addInitScript(() => {
    localStorage.clear()
    window.CapacitorCustomPlatform = { name: 'android' }
  })
  await page.route('https://owner-server.example.invalid/**', async route => {
    requests.push(route.request().url())
    const path = new URL(route.request().url()).pathname
    let data = []
    if (path.endsWith('/api/health')) data = { status: 'ok', database: { ok: true } }
    if (path.includes('/api/hotspots/')) data = { hotspots: [], count: 0, route_length_m: 1000 }
    if (path.endsWith('/api/weather/now')) data = { available: false }
    await route.fulfill({ json: data })
  })
  await page.goto('/')
  await expect(page.locator('.onboard')).toBeVisible()
  await expect(page.locator('.ob-srv')).toHaveValue('')
  await expect(page.locator('.ob-msg')).toContainText('向提供此 App 的管理者取得')
  expect(requests).toEqual([])
  await page.screenshot({ path: '../dist/android-first-run.png' })
  const address = 'https://owner-server.example.invalid/CaseSensitive_Code-123'
  await page.locator('.ob-srv').fill(address)
  await page.locator('.ob-go').click()
  await expect(page.locator('.onboard')).toHaveCount(0)
  expect(requests).toContain(address + '/api/health')
  expect(await page.evaluate(() => localStorage.getItem('serverUrl'))).toBe(address)
  await page.screenshot({ path: '../dist/android-configured-preview.png' })
})
