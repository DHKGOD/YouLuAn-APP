// 家人模式的狀態：常用路線（存在手機）、長輩模式（字放大、提早提醒、語音放慢）
import { emit } from './store.js'

export function savedRoutes() {
  try {
    return JSON.parse(localStorage.getItem('savedRoutes') || '[]')
  } catch {
    return []
  }
}
export function saveRoute(route, name) {
  // 同名路線用新的取代，並放在清單最前面。
  const routes = savedRoutes().filter((savedRoute) => savedRoute.name !== name)
  routes.unshift({ ...route, name, demo: false, savedAt: Date.now() })
  try {
    localStorage.setItem('savedRoutes', JSON.stringify(routes.slice(0, 20)))
  } catch {
    /* 空間不足 */
  }
  emit('saved-routes')
}
export function deleteRoute(name) {
  try {
    const remainingRoutes = savedRoutes().filter((savedRoute) => savedRoute.name !== name)
    localStorage.setItem('savedRoutes', JSON.stringify(remainingRoutes))
  } catch {
    /* ignore */
  }
  emit('saved-routes')
}

export function elderMode() {
  try {
    return localStorage.getItem('elderMode') === '1'
  } catch {
    return false
  }
}
export function setElderMode(enabled) {
  try {
    localStorage.setItem('elderMode', enabled ? '1' : '0')
  } catch {
    /* ignore */
  }
  applyElderMode()
  emit('elder', enabled)
}
export function applyElderMode() {
  document.documentElement.classList.toggle('elder', elderMode())
}
