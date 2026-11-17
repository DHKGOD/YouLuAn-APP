import { test, expect } from '@playwright/test'
import { appendFileSync } from 'node:fs'

const website = process.env.E2E_WEB_BASE_URL
test.use({ browserName: 'webkit', viewport: { width: 393, height: 852 },
  userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1' })
test.skip(!website, '需要執行中的網站入口，請設定E2E_WEB_BASE_URL')

test('iPhone網站自動連線、報告與排行可用，沒有App安裝或背景功能入口', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(() => localStorage.setItem('serverUrl', 'https://old-server.invalid'))
  await page.goto(website)
  await expect(page.locator('.hs-list .hs-cell').first()).toBeVisible()
  await expect(page.locator('.onboard')).toHaveCount(0)
  await expect(page.locator('.tabbar button')).toHaveCount(3)
  await expect(page.locator('[data-act="guardian"], [data-tab="feed"]')).toHaveCount(0)
  await expect(page.locator('a[href$=".ipa"], a[href*="apps.apple.com"]')).toHaveCount(0)
  await page.screenshot({ path: '../logs/iphone-website-home.png' })

  const road = page.locator('.hs-list .hs-cell').first()
  await road.click()
  await road.click()
  await expect(page.locator('.report-hero')).toBeVisible()
  await expect(page.locator('.stat-value').first()).toHaveText(/\d/)
  await expect(page.locator('.bars').first().locator('.bar')).toHaveCount(24)
  await expect(page.getByText('讀取失敗', { exact: true })).toHaveCount(0)
  await page.locator('[data-tab="rank"]').click()
  await expect(page.locator('[data-root="rank"] .rank-list .hs-cell').first()).toBeVisible()

  await page.locator('[data-tab="settings"]').click()
  const settings = page.locator('[data-root="settings"]')
  await expect(settings.locator('[data-gmode], [data-overlay], [data-dev="bg"], [data-dev="nav"], [data-admin], [data-gtest], [data-pref="style"], [data-sw="vibrate"]')).toHaveCount(0)
  await expect(settings).not.toContainText('安裝 Android App')
  await expect(settings).not.toContainText('靈動島')
  await expect(settings).toContainText('iPhone只提供網站操作')
  await expect(settings.locator('.srv')).toHaveAttribute('readonly', '')
  await settings.locator('[data-test]').click()
  await expect(settings.locator('.server-status')).toContainText('已連線')
  await expect(settings.locator('.server-status')).not.toContainText('undefined')
  await settings.locator('[data-family]').click()
  await expect(page.getByText('長輩模式', { exact: true }).first()).toBeVisible()
  expect(errors).toEqual([])
})

test('網站可同源分享路線，iPhone模擬切到背景即暫停', async ({ page }) => {
  await page.goto(website)
  await expect(page.locator('.hs-list .hs-cell').first()).toBeVisible()
  const shared = await page.evaluate(async () => {
    const base = document.querySelector('meta[name="youluan-api-path"]').content
    const response = await fetch(base + '/api/routes', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'E2E Safari 網站分享', mode: 'foot', start_name: '輔大', end_name: '新莊',
        points: [[25.0363, 121.4318], [25.0361, 121.4525]], distance_m: 2100, duration_s: 1600, for_elder: false }) })
    return { status: response.status, data: await response.json() }
  })
  expect(shared.status).toBe(201)
  expect(shared.data.code).toHaveLength(6)
  appendFileSync('../logs/ios-website-e2e-codes.txt', shared.data.code + '\n')
  await page.locator('[data-act="walk"]').click()
  await expect(page.locator('.walk-panel')).toBeVisible()
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await expect(page.locator('.walk-next')).toHaveText('模擬已暫停，回來後按播放繼續')
  await page.locator('.walk-panel [data-w="stop"]').click()
})
