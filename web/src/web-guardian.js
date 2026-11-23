import { api } from './api.js'
import { alertPrefs, levelPasses } from './alerts.js'
import { elderMode } from './family.js'
import { L } from './map-utils.js'
import { LEVEL, toast } from './ui.js'
import { playAlertSound, prepareAlertSound, speak } from './walk.js'

const DISTANCES = { foot: 60, bike: 120, car: 220 }
const SEARCH_RADIUS = 750
const REFRESH_DISTANCE = 120
const MIN_REQUEST_GAP = 5000
const MAX_POSITION_AGE = 20000
const ALERT_COOLDOWN = 10 * 60 * 1000

export function createWebGuardian({ onStatus, onPosition, onOpenReport }) {
  let enabled = false
  let watchId = null
  let generation = 0
  let mode = 'foot'
  let location = null
  let area = null
  let pending = false
  let lastRequest = -Infinity
  let lastAlert = -Infinity
  const alerted = new Map()

  const active = (run) => enabled && !document.hidden && generation === run

  function checkHotspots() {
    if (!location || !area || Date.now() - location.timestamp > MAX_POSITION_AGE) return
    const prefs = alertPrefs()
    const threshold = DISTANCES[mode] * prefs.distance * (elderMode() ? 1.5 : 1)
    if (location.point.distanceTo(area.center) + threshold > SEARCH_RADIUS) return
    const now = Date.now()
    if (now - lastAlert < 8000) return
    let closest = null
    let nearest = threshold
    for (const road of area.hotspots) {
      if (!levelPasses(road.level, prefs) || now - (alerted.get(road.id) ?? -Infinity) < ALERT_COOLDOWN) continue
      const distance = location.point.distanceTo([road.lat, road.lon])
      if (distance <= nearest) {
        closest = road
        nearest = distance
      }
    }
    if (!closest) return
    lastAlert = now
    alerted.set(closest.id, now)
    const meters = Math.max(0, Math.round(nearest / 10) * 10)
    const label = LEVEL[closest.level]?.label || '注意'
    toast(`附近${label}路口・${closest.name}・約 ${meters} 公尺`, {
      icon: 'warningFill', color: 'var(--red)', ms: 6500, onClick: () => onOpenReport(closest),
    })
    if (prefs.sound) playAlertSound()
    if (prefs.voice) speak(`注意，附近約${meters}公尺有${label}路口`)
  }

  async function onLocation(position, run) {
    if (!active(run)) return
    const { latitude, longitude, accuracy } = position.coords
    if (!Number.isFinite(accuracy) || accuracy > 60 || Date.now() - position.timestamp > MAX_POSITION_AGE) {
      location = null
      onStatus('定位精度不足，暫停提醒')
      return
    }
    const point = L.latLng(latitude, longitude)
    const first = !location && !area && lastRequest === -Infinity
    location = { point, timestamp: position.timestamp }
    onPosition(point, first)
    const moved = !area || area.center.distanceTo(point) >= REFRESH_DISTANCE
    const expired = area && Date.now() - area.loadedAt >= 60000
    if (area) checkHotspots()
    if (pending || (!moved && !expired) || Date.now() - lastRequest < MIN_REQUEST_GAP) return
    lastRequest = Date.now()
    pending = true
    onStatus('正在查詢附近路口')
    const query = new URLSearchParams({ lat: latitude, lon: longitude, radius: SEARCH_RADIUS, complete: 'true' })
    try {
      const data = await api(`/api/hotspots/near?${query}`, { timeout: 10000 })
      if (!active(run)) return
      area = { center: point, hotspots: data.hotspots, loadedAt: Date.now() }
      if (location) {
        onStatus('前景提醒中')
        checkHotspots()
      }
    } catch {
      if (active(run)) onStatus('暫時無法查詢路口，稍後重試')
    } finally {
      if (active(run)) pending = false
    }
  }

  function clearLocation() {
    generation += 1
    if (watchId !== null) navigator.geolocation.clearWatch(watchId)
    watchId = null
    location = null
    area = null
    pending = false
    lastRequest = -Infinity
  }

  function stop() {
    enabled = false
    clearLocation()
    alerted.clear()
    lastAlert = -Infinity
    onStatus('未開啟')
  }

  function watch() {
    const run = generation
    onStatus('等候定位')
    watchId = navigator.geolocation.watchPosition(
      (position) => onLocation(position, run),
      (error) => {
        if (!active(run)) return
        if (error.code === 1) {
          stop()
          onStatus('請允許網站定位')
        } else {
          location = null
          onStatus('等候可用的定位訊號')
        }
      },
      { enableHighAccuracy: true, maximumAge: 3000, timeout: 15000 }
    )
  }

  document.addEventListener('visibilitychange', () => {
    if (!enabled) return
    if (document.hidden) {
      clearLocation()
      onStatus('網頁切到背景，提醒暫停')
    } else if (watchId === null) watch()
  })
  window.addEventListener('pagehide', () => {
    if (enabled) stop()
  })

  return {
    get enabled() { return enabled },
    start(selectedMode) {
      if (enabled) return
      if (!window.isSecureContext || !navigator.geolocation) {
        onStatus('此瀏覽器無法定位，仍可瀏覽地圖')
        return
      }
      mode = selectedMode
      enabled = true
      if (alertPrefs().sound) prepareAlertSound()
      watch()
    },
    stop,
  }
}
