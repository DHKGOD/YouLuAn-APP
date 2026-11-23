// 即時天氣與「自動」天候模式：後端代查中央氣象署（最近雨量站＋鄉鎮降雨機率），下雨時自動切到雨天模式
import { Geolocation } from '@capacitor/geolocation'
import { api } from './api.js'
import { icon } from './icons.js'
import { emit, on, routeOrDemo, setMode, state } from './store.js'
import { actionSheet, toast } from './ui.js'

const REFRESH_MS = 10 * 60 * 1000 // 氣象署每 10 分鐘更新
const KEY = 'weatherAuto'

export const live = { available: null, data: null, at: 0, loading: false }
let timer = null

function savedAuto() {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}
state.weatherAuto = savedAuto()

async function position() {
  try {
    // 只在已授權時用定位，不在開 App 時跳出權限詢問
    if ((await Geolocation.checkPermissions()).location !== 'granted')
      throw new Error('no permission')
    const positionResult = await Geolocation.getCurrentPosition({
      enableHighAccuracy: false,
      timeout: 5000,
      maximumAge: 5 * 60 * 1000,
    })
    return { lat: positionResult.coords.latitude, lon: positionResult.coords.longitude, from: 'gps' }
  } catch {
    const start = routeOrDemo().start // 沒有定位（平板、網頁）→ 用路線起點（探索模式用 Demo 起點）
    return { lat: start.lat, lon: start.lon, from: 'route' }
  }
}

/** 取得即時天氣；自動模式下依建議切換晴天／雨天。 */
let inflight = null
let wantAnnounce = false
export function refreshLive({ announce = false } = {}) {
  // 同時有多處查天氣時，共用尚未完成的請求。
  if (announce) wantAnnounce = true
  if (inflight === null) {
    inflight = doRefresh().finally(() => {
      inflight = null
      wantAnnounce = false
    })
  }
  return inflight
}

async function doRefresh() {
  live.loading = true
  try {
    const location = await position()
    const weatherData = await api(`/api/weather/now?lat=${location.lat.toFixed(4)}&lon=${location.lon.toFixed(4)}`, {
      timeout: 25000,
    })
    live.available = !!weatherData.available
    live.data = weatherData.available ? { ...weatherData, from: location.from } : null
    live.at = Date.now()
    if (!weatherData.available && state.weatherAuto) setAuto(false, { silent: true })
    else if (state.weatherAuto) apply(wantAnnounce)
    emit('live-weather', live)
    return live.data
  } catch {
    emit('live-weather', live) // 失敗時保留上次結果
    return null
  } finally {
    live.loading = false
  }
}

function apply(announce) {
  const weatherData = live.data
  if (!weatherData) return
  const previousWeather = state.weather
  if (weatherData.suggested_mode !== previousWeather) setMode({ weather: weatherData.suggested_mode })
  if (weatherData.suggested_mode === 'rain' && (previousWeather !== 'rain' || announce)) {
    toast(`${weatherData.reason}，已切換雨天模式`, { icon: 'rain', color: 'var(--indigo)', ms: 4200 })
  } else if (announce) {
    toast(`${weatherData.station.town}目前${weatherData.forecast?.weather || '沒有下雨'}，顯示晴天時的危險路口`, {
      icon: 'sun',
      color: 'var(--orange)',
      ms: 3600,
    })
  }
}

function setAuto(enabled, { silent = false } = {}) {
  state.weatherAuto = enabled
  try {
    localStorage.setItem(KEY, enabled ? '1' : '0')
  } catch {
    /* 不影響使用 */
  }
  clearInterval(timer)
  if (enabled) {
    timer = setInterval(() => refreshLive(), REFRESH_MS)
  } else {
    timer = null
  }
  if (!enabled && !silent) emit('mode', {})
}

/** 天候膠囊的外觀（地圖頁、排行頁共用）。 */
export function renderWeatherChip(chip) {
  const weather = state.weather
  let label = '全部天候'
  if (weather === 'rain') label = '雨天'
  else if (weather === 'clear') label = '晴天'

  let iconName = 'sun'
  if (weather === 'rain') iconName = 'rain'
  else if (state.weatherAuto) iconName = 'sparkles'
  chip.className = `chip${weather !== 'all' ? ' on' : ''}${weather === 'rain' ? ' rain' : ''}`
  chip.innerHTML = `${icon(iconName)}${
    state.weatherAuto ? `自動・${label}` : label
  }<span class="caret">${icon('chevronDown')}</span>`
}

function liveLine() {
  const weatherData = live.data
  if (!weatherData) return ''
  const pop = weatherData.pop_percent != null ? `・降雨機率 ${weatherData.pop_percent}%` : ''
  const rain = weatherData.rain_1h_mm != null ? `・1 小時雨量 ${weatherData.rain_1h_mm} mm` : ''
  return `${weatherData.station.town}${weatherData.forecast?.weather ? ' ' + weatherData.forecast.weather : ''}${pop}${rain}`
}

/** 天候模式動作表（有氣象署資料時多一個「自動」選項）。 */
export async function pickWeather() {
  if (live.available === null && !live.loading) refreshLive() // 背景先查，不擋住動作表
  const auto = live.available !== false
  const options = []
  if (auto) {
    options.push({ value: 'auto', label: '自動（依氣象署即時天氣）', icon: 'sparkles' })
  }
  options.push(
    { value: 'all', label: '全部天候' },
    { value: 'clear', label: '晴天／陰天', icon: 'sun' },
    { value: 'rain', label: '雨天', icon: 'rain' },
  )
  const line = liveLine()
  const choice = await actionSheet({
    title: '天候模式',
    message: line ? `目前 ${line}` : '依事故發生時的天候篩選危險路口',
    value: state.weatherAuto ? 'auto' : state.weather,
    options,
  })
  if (!choice) return
  if (choice === 'auto') {
    if (state.weatherAuto) return
    setAuto(true)
    emit('mode', {})
    const weatherData = await refreshLive({ announce: true })
    if (!weatherData) {
      setAuto(false, { silent: true })
      emit('mode', {})
      toast('暫時取不到氣象署資料，請稍後再試', { icon: 'warning', color: 'var(--red)', ms: 3600 })
    }
    return
  }
  const wasAuto = state.weatherAuto
  if (wasAuto) setAuto(false, { silent: true })
  if (choice !== state.weather) setMode({ weather: choice })
  else if (wasAuto) emit('mode', {})
}

/** App 啟動時呼叫：恢復自動模式、查一次可用性。 */
export function initWeather() {
  if (state.weatherAuto) setAuto(true, { silent: true })
  refreshLive()
  on((type) => {
    if (type === 'server-changed') refreshLive()
  })
}
