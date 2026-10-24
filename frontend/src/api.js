// 伺服器位址與 API 呼叫。位址存在本機（換到雲端不用重新打包 APK，只要在設定頁改位址）。
import { Capacitor } from '@capacitor/core'

const KEY = 'serverUrl'

export const isNative = () => Capacitor.isNativePlatform()

/** 網頁版若由後端提供（http://IP:8000/），預設連同一個來源；App 版需要在設定頁輸入。 */
export function defaultServer() {
  if (!isNative() && location.protocol.startsWith('http') && location.port !== '5173')
    return location.origin
  return import.meta.env.VITE_DEFAULT_SERVER || ''
}

export function getServer() {
  try {
    return localStorage.getItem(KEY) || defaultServer()
  } catch {
    return defaultServer()
  }
}

export function setServer(url) {
  const clean = normalize(url)
  try {
    localStorage.setItem(KEY, clean)
  } catch {
    /* 無痕模式等情況 */
  }
  return clean
}

export function normalize(url) {
  // 中文輸入法常打出全形「：．／」或「。」，一律轉成半形並去掉空白
  let serverUrl = (url || '')
    .replace(/[！-～]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0))
    .replace(/[。､、]/g, '.')
    .replace(/\s+/g, '')
    .replace(/\/+$/, '')
  if (serverUrl && !/^https?:\/\//i.test(serverUrl)) serverUrl = 'http://' + serverUrl
  // 只輸入 IP 時自動補上預設 port 8000
  if (/^https?:\/\/[\d.]+$/i.test(serverUrl)) serverUrl += ':8000'
  return serverUrl
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

export async function api(path, { method = 'GET', body, timeout = 12000, server } = {}) {
  const base = server ?? getServer()
  if (!base) throw new ApiError('尚未設定伺服器位址', 0)
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const response = await fetch(base + path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
    const data = await response.json().catch(() => null)
    if (!response.ok) {
      let message = `伺服器錯誤（${response.status}）`
      if (data?.detail) {
        message = '資料格式不正確'
        if (typeof data.detail === 'string') message = data.detail
      }
      throw new ApiError(message, response.status)
    }
    return data
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error.name === 'AbortError') throw new ApiError('連線逾時，請確認手機與電腦在同一個 Wi-Fi', 0)
    throw new ApiError('無法連線到伺服器，請到「設定」確認位址', 0)
  } finally {
    clearTimeout(timer)
  }
}

export function deviceId() {
  try {
    let id = localStorage.getItem('deviceId')
    if (!id) {
      id = 'dev-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4)
      localStorage.setItem('deviceId', id)
    }
    return id
  } catch {
    return 'dev-anon'
  }
}
