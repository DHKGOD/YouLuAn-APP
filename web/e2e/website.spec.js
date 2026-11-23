import { test, expect } from '@playwright/test'

const website = process.env.E2E_WEB_BASE_URL
test.skip(!website, '設定 E2E_WEB_BASE_URL 以測試已部署的網頁')

test('模擬途中切換五種交通圖示和速度，並保留倍率及進度', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('alertPrefs', JSON.stringify({ voice: false, sound: false })))
  await page.clock.install()
  await page.goto(website)
  await expect(page.locator('.hs-list .hs-cell').first()).toBeVisible()
  await page.locator('[data-act="walk"]').click()
  const panel = page.locator('.walk-panel')
  const slider = panel.getByRole('slider', { name: '交通方式' })
  const speed = panel.locator('.walk-speed-value')
  await expect(slider).toBeVisible()
  for (const [name, icon, kmh] of [
    ['步行', 'walk', 4.5], ['腳踏車', 'bike', 16], ['機車', 'scooter', 36],
    ['開車', 'car', 54], ['高鐵／快線捷運', 'train', 250],
  ]) {
    await panel.getByRole('button', { name, exact: true }).click()
    await expect(page.locator(`[data-vehicle-icon="${icon}"] svg`)).toBeVisible()
    await expect(speed).toHaveText(`${kmh} km/h × 4 倍速`)
  }
  await expect(panel.locator('.walk-rail-note')).toBeVisible()
  await panel.getByRole('tab', { name: '10×', exact: true }).click()
  await expect(speed).toHaveText('250 km/h × 10 倍速')
  await slider.press('Home')
  await expect(speed).toHaveText('4.5 km/h × 10 倍速')
  await panel.getByRole('tab', { name: '1×', exact: true }).click()
  const progress = () => panel.locator('.walk-prog').evaluate(bar => parseFloat(bar.style.width))
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 500))
  const before = await progress()
  await page.clock.runFor(1000)
  const walking = await progress()
  expect(walking).toBeGreaterThan(before)
  await slider.evaluate(input => {
    input.value = input.max
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  expect(await progress()).toBe(walking)
  await page.clock.runFor(1000)
  expect((await progress()) - walking).toBeGreaterThan((walking - before) * 30)
  await expect(panel.locator('.walk-alert')).toBeHidden()
})

test('共用網址提供地圖、報告、排行和網頁設定', async ({ page }) => {
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      await page.addInitScript(() => localStorage.setItem('serverUrl', 'https://old-server.invalid'))
      await page.goto(website)
      const road = page.locator('.hs-list .hs-cell').first()
      await expect(road).toBeVisible()
      await expect(page.locator('.onboard, [data-act="guardian"], [data-tab="feed"]')).toHaveCount(0)
      await expect(page.locator('[data-act="live-location"]')).toBeVisible()
      await road.click()
      await road.click()
      await expect(page.locator('.report-hero')).toBeVisible()
      await expect(page.locator('.stat-value').first()).toHaveText(/\d/)
      await page.locator('[data-tab="rank"]').click()
      await expect(page.locator('[data-root="rank"] .rank-list .hs-cell').first()).toBeVisible()
      await page.locator('[data-tab="settings"]').click()
      const settings = page.locator('[data-root="settings"]')
      await expect(settings.locator('[data-gmode], [data-overlay], [data-admin], [data-sw="vibrate"]')).toHaveCount(0)
      await expect(settings).toContainText('網頁版，無需安裝')
      await expect(settings).toContainText('鎖屏及切到背景時暫停提醒')
      await expect(settings.locator('.srv')).toHaveAttribute('readonly', '')
      await settings.locator('[data-test]').click()
      await expect(settings.locator('.server-status')).toContainText('已連線')
      await expect(settings.locator('.ai-ver')).toContainText('情境預測')
      await settings.locator('[data-family]').click()
      await expect(page.getByText('長輩模式', { exact: true }).first()).toBeVisible()
      expect(errors).toEqual([])
})

test('定位超過提醒範圍時保持安靜，靠近才提醒，切到背景停止定位', async ({ page, context }) => {
  const start = { latitude: 25.0363, longitude: 121.4318, accuracy: 8 }
  const intersection = { latitude: 25.0376, longitude: start.longitude, accuracy: 8 }
  await context.setGeolocation(start)
  await page.addInitScript(() => {
    localStorage.setItem('alertPrefs', JSON.stringify({ voice: true, sound: true }))
    window.testAlerts = { tones: 0, spoken: [] }
    const param = () => ({ setValueAtTime() {}, exponentialRampToValueAtTime() {} })
    window.AudioContext = class {
      currentTime = 0
      destination = {}
      async resume() {}
      createGain() { return { gain: param(), connect() {} } }
      createOscillator() {
        return { frequency: param(), connect(target) { return target }, stop() {},
          start() { window.testAlerts.tones++ } }
      }
    }
    Object.defineProperty(window, 'speechSynthesis', {
      value: { cancel() {}, speak(utterance) { window.testAlerts.spoken.push(utterance.text) } },
    })
    window.SpeechSynthesisUtterance = class {
      constructor(text) { this.text = text }
    }
  })
  let requests = 0
  await page.route('**/api/hotspots/near?*', async route => {
    const url = new URL(route.request().url())
    if (url.searchParams.get('complete') !== 'true') return route.continue()
    requests++
    await route.fulfill({ json: { hotspots: [{ id: 1, name: '定位測試路口', level: 'high',
      lat: intersection.latitude, lon: intersection.longitude }] } })
  })
  await page.goto(website)
  await expect(page.locator('.hs-list .hs-cell').first()).toBeVisible()
  const button = page.locator('[data-act="live-location"]')
  await button.click()
  await page.getByRole('button', { name: '步行', exact: true }).click()
  await expect(button).toContainText('前景提醒中')
  await expect(page.getByText('定位測試路口', { exact: false })).toHaveCount(0)
  await context.setGeolocation({ ...intersection, accuracy: 250 })
  await expect(button).toContainText('定位精度不足，暫停提醒')
  expect(await page.evaluate(() => window.testAlerts)).toEqual({ tones: 0, spoken: [] })
  await context.setGeolocation(intersection)
  await expect(page.locator('.toast').filter({ hasText: '附近高風險路口・定位測試路口' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.testAlerts.tones)).toBe(2)
  expect(await page.evaluate(() => window.testAlerts.spoken)).toEqual([expect.stringContaining('高風險路口')])

  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await expect(button).toContainText('網頁切到背景，提醒暫停')
  const before = requests
  await context.setGeolocation(start)
  expect(requests).toBe(before)
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await expect(button).toContainText('前景提醒中')
  expect(requests).toBeGreaterThan(before)
  await button.click()
  await expect(button).toHaveAttribute('aria-pressed', 'false')
  await expect(button).toContainText('未開啟')
})

test('沒有定位授權時仍能查看地圖、模擬行走', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.geolocation.watchPosition = (_, failure) => {
      setTimeout(() => failure({ code: 1 }), 0)
      return 0
    }
    navigator.geolocation.clearWatch = () => {}
    localStorage.setItem('alertPrefs', JSON.stringify({ voice: false, sound: false }))
  })
  await page.goto(website)
  await expect(page.locator('.hs-list .hs-cell').first()).toBeVisible()
  const button = page.locator('[data-act="live-location"]')
  await button.click()
  await page.getByRole('button', { name: '步行', exact: true }).click()
  await expect(button).toContainText('請允許網站定位')
  await expect(button).toHaveAttribute('aria-pressed', 'false')
  await page.locator('[data-act="walk"]').click()
  await expect(page.locator('.walk-panel')).toBeVisible()
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await expect(page.locator('.walk-next')).toHaveText('模擬已暫停，回來後按播放繼續')
})
