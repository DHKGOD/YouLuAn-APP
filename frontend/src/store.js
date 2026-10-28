// 全域狀態：天候／時段模式、目前路線

import DEMO_ROUTE from './data/demo-route.json'

const listeners = new Set()

export const MODE_LABEL = { foot: '步行', bike: '自行車', car: '汽機車' }
export const DEMO = { ...DEMO_ROUTE, mode: 'foot', demo: true }

function loadRoute() {
  try {
    const raw = localStorage.getItem('route')
    if (raw === 'none') return null // 探索模式：沒有路線，自由瀏覽地圖上的危險路口
    const r = JSON.parse(raw || 'null')
    if (r?.points?.length >= 2 && r.start && r.end) return r
  } catch {
    /* 格式不對就用 Demo */
  }
  return DEMO
}

/** 需要一個位置或路線、但目前是探索模式（沒有路線）時，用 Demo 路線代替。 */
export const routeOrDemo = () => state.route || DEMO

export const state = { route: loadRoute(), weather: 'all', period: 'all' }

export function on(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}
export function emit(type, payload) {
  listeners.forEach((fn) => fn(type, payload))
}

/** 設定路線；傳 null 進入探索模式（沒有目的地，看地圖範圍內的危險路口）。 */
export function setRoute(route) {
  state.route = route
  try {
    if (!route) localStorage.setItem('route', 'none')
    else if (route.demo) localStorage.removeItem('route')
    else localStorage.setItem('route', JSON.stringify(route))
  } catch {
    /* 儲存失敗不影響使用 */
  }
  emit('route', route)
}

export function setMode(patch) {
  Object.assign(state, patch)
  emit('mode', patch)
}

export const WEATHER_OPTS = [
  { value: 'all', label: '全部' },
  { value: 'clear', label: '晴天', icon: 'sun' },
  { value: 'rain', label: '雨天', icon: 'rain' },
]
export const PERIOD_OPTS = [
  { value: 'all', label: '全天' },
  { value: 'morning', label: '早上' },
  { value: 'day', label: '白天' },
  { value: 'evening', label: '傍晚' },
  { value: 'night', label: '夜間' },
]
export const PERIOD_HINT = {
  all: '全天',
  morning: '6–9 點',
  day: '10–15 點',
  evening: '16–19 點',
  night: '20–5 點',
}
