// 模擬行走：藍點沿目前路線移動，接近危險路口時「語音＋提示音＋紅框」提醒
// （平板常沒有 GPS 與震動，所以用模擬位置與畫面、聲音提醒）
import { App as CapApp } from '@capacitor/app'
import { TextToSpeech } from '@capacitor-community/text-to-speech'
import { isNative } from './api.js'
import { guardianState, handoffWalk, takeBackWalk, walkAlert } from './guardian.js'
import { alertPrefs, levelPasses } from './alerts.js'
import { icon } from './icons.js'
import { L, simulationMarker } from './map-utils.js'
import { $, LEVEL, el, esc, fmt, haptic, segmented } from './ui.js'

const TRANSPORT = [
  { routeMode: 'foot', icon: 'walk', label: '步行', kmh: 4.5, alertMeters: 70, tip: '過馬路前左右看，別低頭看手機' },
  { routeMode: 'bike', icon: 'bike', label: '腳踏車', kmh: 16, alertMeters: 120, tip: '請減速，注意左右來車與開車門' },
  { routeMode: 'bike', icon: 'scooter', label: '機車', kmh: 36, alertMeters: 180, tip: '接近路口請減速，注意轉彎車' },
  { routeMode: 'car', icon: 'car', label: '開車', kmh: 54, alertMeters: 250, tip: '請減速，注意轉彎車與機車' },
  { routeMode: 'transit', icon: 'train', label: '高鐵', title: '高鐵／快線捷運', kmh: 250, alertMeters: 0 },
]

function cumulative(points) {
  const R = 6371000
  const out = [0]
  for (let i = 1; i < points.length; i++) {
    const [a, b] = [points[i - 1], points[i]]
    const dLat = ((b[0] - a[0]) * Math.PI) / 180
    const dLon = ((b[1] - a[1]) * Math.PI) / 180
    const x =
      Math.sin(dLat / 2) ** 2 +
      Math.cos((a[0] * Math.PI) / 180) * Math.cos((b[0] * Math.PI) / 180) * Math.sin(dLon / 2) ** 2
    out.push(out[i - 1] + 2 * R * Math.asin(Math.sqrt(x)))
  }
  return out
}

function positionAt(points, cum, d) {
  let i = cum.findIndex((c) => c >= d)
  if (i <= 0) return points[i === 0 ? 0 : points.length - 1]
  const t = (d - cum[i - 1]) / Math.max(1e-6, cum[i] - cum[i - 1])
  return [
    points[i - 1][0] + (points[i][0] - points[i - 1][0]) * t,
    points[i - 1][1] + (points[i][1] - points[i - 1][1]) * t,
  ]
}

let audioCtx
export function prepareAlertSound() {
  try {
    audioCtx ??= new (window.AudioContext || window.webkitAudioContext)()
    audioCtx.resume().catch(() => {})
  } catch {
    /* 畫面提醒不依賴音效裝置。 */
  }
}

export { beep as playAlertSound }
function beep() {
  try {
    audioCtx ??= new (window.AudioContext || window.webkitAudioContext)()
    const t0 = audioCtx.currentTime
    ;[0, 0.22].forEach((off) => {
      const o = audioCtx.createOscillator()
      const g = audioCtx.createGain()
      o.type = 'sine'
      o.frequency.setValueAtTime(880, t0 + off)
      o.frequency.exponentialRampToValueAtTime(1320, t0 + off + 0.12)
      g.gain.setValueAtTime(0.0001, t0 + off)
      g.gain.exponentialRampToValueAtTime(0.35, t0 + off + 0.02)
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + off + 0.18)
      o.connect(g).connect(audioCtx.destination)
      o.start(t0 + off)
      o.stop(t0 + off + 0.2)
    })
  } catch {
    /* 沒有音效裝置 */
  }
}

export async function speak(text) {
  try {
    if (isNative()) {
      await TextToSpeech.stop().catch(() => {})
      await TextToSpeech.speak({
        text,
        lang: 'zh-TW',
        rate: 1.0,
        pitch: 1.0,
        volume: 1.0,
        category: 'ambient',
      })
    } else if ('speechSynthesis' in window) {
      speechSynthesis.cancel()
      const u = new SpeechSynthesisUtterance(text)
      u.lang = 'zh-TW'
      speechSynthesis.speak(u)
    }
  } catch {
    /* 沒有中文語音時只用提示音與紅框 */
  }
}

export function startWalk({
  map,
  hotspots,
  route: ROUTE,
  onOpenReport,
  onStop,
  speed: initialSpeed,
}) {
  const prefs = alertPrefs() // 設定頁「危險通知」
  if (!map || document.querySelector('.walk-panel')) return
  const cum = cumulative(ROUTE.points)
  const total = cum.at(-1)
  let transportIndex = Math.max(0, TRANSPORT.findIndex((mode) => mode.routeMode === ROUTE.mode))
  let transport = TRANSPORT[transportIndex]
  let dist = 0
  let speed = [1, 4, 10, 30].includes(initialSpeed) ? initialSpeed : 4
  let playing = true
  let last = performance.now()
  const alerted = new Set()
  let frame = null
  let alertTimer = null
  const orderedHotspots = hotspots.filter((road) => Number.isFinite(road.along_m))
    .sort((a, b) => a.along_m - b.along_m)
  const marker = L.marker(ROUTE.points[0], { icon: simulationMarker(transport.icon), zIndexOffset: 2000 }).addTo(map)
  try {
    map.flyTo(ROUTE.points[0], 17, { duration: 0.8 })
  } catch {
    map.setView(ROUTE.points[0], 17, { animate: false })
  }

  const panel = el(`
    <div class="walk-panel" style="position:fixed;left:12px;right:12px;bottom:calc(var(--tabbar-h) + 12px);z-index:60;max-width:560px;margin:0 auto">
      <div class="walk-alert" style="display:none;margin-bottom:10px"></div>
      <div class="glass-card" style="flex-direction:column;align-items:stretch;gap:10px;padding:14px">
        <div style="display:flex;align-items:center;gap:12px">
          <span class="cell-icon walk-mode-icon" style="background:var(--blue);width:40px;height:40px;border-radius:12px;font-size:22px">${icon(transport.icon)}</span>
          <div style="flex:1;min-width:0">
            <div class="t-headline walk-title"></div>
            <div class="t-footnote c-2 walk-speed-value"></div>
            <div class="t-footnote c-2 walk-next">準備出發</div>
          </div>
          <button class="fab" data-w="toggle" style="border-radius:50%;width:44px;height:44px;background:var(--fill)">${icon(
            'pause'
          )}</button>
          <button class="fab" data-w="stop" style="border-radius:50%;width:44px;height:44px;background:var(--fill);color:var(--red)">${icon(
            'xmark'
          )}</button>
        </div>
        <div class="hbar-track" style="height:6px"><div class="walk-prog" style="height:100%;width:0;background:var(--blue);border-radius:3px"></div></div>
        <div class="walk-transport">
          <input type="range" min="0" max="${TRANSPORT.length - 1}" step="1" value="${transportIndex}" aria-label="交通方式">
          <div class="walk-transport-labels">
            ${TRANSPORT.map((mode, i) => `<button type="button" data-transport="${i}" aria-label="${mode.title || mode.label}">${mode.label}</button>`).join('')}
          </div>
          <div class="t-footnote c-2 walk-rail-note" hidden>沿目前路線比較快速軌道的速度，道路提醒暫停。</div>
        </div>
        <div class="seg-speed"></div>
      </div>
    </div>`)
  document.body.appendChild(panel)
  const slider = $('.walk-transport input', panel)
  function renderTransport() {
    const label = transport.title || transport.label
    $('.walk-title', panel).textContent = `模擬${label}`
    $('.walk-speed-value', panel).textContent = `${transport.kmh} km/h × ${speed} 倍速`
    slider.value = String(transportIndex)
    slider.setAttribute('aria-valuetext', `${label}，${transport.kmh} 公里每小時`)
    $('.walk-rail-note', panel).hidden = transport.routeMode !== 'transit'
    panel.querySelectorAll('[data-transport]').forEach((button) => {
      button.setAttribute('aria-pressed', String(+button.dataset.transport === transportIndex))
    })
  }
  function changeTransport(index) {
    if (index === transportIndex || !TRANSPORT[index]) return
    transportIndex = index
    transport = TRANSPORT[index]
    last = performance.now()
    marker.setIcon(simulationMarker(transport.icon))
    $('.walk-mode-icon', panel).innerHTML = icon(transport.icon)
    if (transport.routeMode === 'transit') {
      clearAlert()
      window.speechSynthesis?.cancel()
    }
    renderTransport()
  }
  slider.addEventListener('input', () => changeTransport(Number(slider.value)))
  renderTransport()
  $('.seg-speed', panel).replaceWith(
    segmented(
      [
        { value: '1', label: '1×' },
        { value: '4', label: '4×' },
        { value: '10', label: '10×' },
        { value: '30', label: '30×' },
      ],
      String(speed),
      (v) => {
        speed = +v
        last = performance.now()
        renderTransport()
      }
    )
  )

  // 第一次互動時解鎖音效（瀏覽器規定要使用者觸發）
  if (prefs.sound) prepareAlertSound()

  function clearAlert() {
    clearTimeout(alertTimer)
    frame?.remove()
    frame = null
    $('.walk-alert', panel).style.display = 'none'
  }

  function showAlert(h, meters) {
    if (isNative() && prefs.vibrate) haptic(300)
    if (prefs.sound) beep()
    walkAlert(h, meters, transport.tip)
    // 語音短一點：只說距離與風險等級（和背景守護一致），路名與事故數看畫面上的紅色卡片
    const m = Math.round(meters / 10) * 10
    if (prefs.voice)
      speak(`注意，前方${m}公尺，${{ high: '高風險', medium: '中風險' }[h.level] || '注意'}路口`)
    frame?.remove()
    frame = document.body.appendChild(el('<div class="alert-frame"></div>'))
    const box = $('.walk-alert', panel)
    box.style.display = 'block'
    box.innerHTML = `
      <button class="glass-card" data-w="open" style="width:100%;text-align:left;border:2px solid var(--red);animation:pop-in .4s var(--spring)">
        <span class="cell-icon" style="background:var(--red);width:40px;height:40px;border-radius:12px;font-size:22px">${icon(
          'warningFill'
        )}</span>
        <span style="flex:1;min-width:0">
          <span class="t-headline" style="display:block;color:var(--red)">前方危險路口・${
            LEVEL[h.level].label
          }</span>
          <span class="t-subhead" style="display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(
            h.name
          )}・${h.filtered_count} 件事故</span>
        </span>
        <span class="chev">${icon('chevronRight')}</span>
      </button>`
    box.firstElementChild.__h = h
    clearTimeout(alertTimer)
    alertTimer = setTimeout(clearAlert, 6000)
  }

  function tick(now) {
    if (!panel.isConnected) return
    const dt = Math.min(0.1, (now - last) / 1000)
    last = now
    if (playing) {
      const previousDist = dist
      dist = Math.min(total, dist + (transport.kmh / 3.6) * speed * dt)
      const pos = positionAt(ROUTE.points, cum, dist)
      marker.setLatLng(pos)
      try {
        if (!map.getBounds().pad(-0.25).contains(pos))
          map.panTo(pos, { animate: true, duration: 0.5 })
      } catch {
        /* MapLibre 動畫中偶爾換算座標失敗：下一格再跟 */
      }
      $('.walk-prog', panel).style.width = `${(dist / total) * 100}%`
      const ahead = orderedHotspots.find((road) => road.along_m >= dist - 10)
      if (transport.routeMode === 'transit') {
        $('.walk-next', panel).textContent = `剩 ${fmt.dist(total - dist)}`
      } else {
        $('.walk-next', panel).textContent = ahead
          ? `下一個危險路口：${ahead.name}（${fmt.dist(Math.max(0, ahead.along_m - dist))}）`
          : `沒有更多危險路口・剩 ${fmt.dist(total - dist)}`
        // 加速時也比對這一格移動經過的路口，避免跨過才檢查。
        const danger = orderedHotspots.find((road) => road.along_m >= previousDist - 10
          && road.along_m <= dist + transport.alertMeters * prefs.distance
          && levelPasses(road.level, prefs))
        if (danger && !alerted.has(danger.id)) {
          alerted.add(danger.id)
          showAlert(danger, Math.max(0, danger.along_m - dist))
        }
      }
      if (dist >= total) {
        playing = false
        if (prefs.voice) speak(`已抵達目的地，${ROUTE.end.name}`)
        $('.walk-next', panel).textContent = `已抵達 ${ROUTE.end.name}`
        $('[data-w="toggle"]', panel).innerHTML = icon('refresh')
      }
    }
    requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)

  panel.addEventListener('click', (e) => {
    const modeButton = e.target.closest('[data-transport]')
    if (modeButton) return changeTransport(Number(modeButton.dataset.transport))
    const w = e.target.closest('[data-w]')?.dataset.w
    if (w === 'toggle') {
      if (dist >= total) {
        dist = 0
        alerted.clear()
        playing = true
      } else {
        playing = !playing
      }
      last = performance.now()
      e.target.closest('[data-w]').innerHTML = icon(playing ? 'pause' : 'play')
    }
    if (w === 'stop') stop()
    if (w === 'open') onOpenReport?.(e.target.closest('[data-w]').__h)
  })

  /* 切到背景（按主畫面鍵、開 Google 地圖）：交給原生服務繼續模擬並跳通知 */
  let handoff = null // { base: 交出時已走的距離 }
  let handing = null // 交接中的 Promise（避免切換太快時順序錯亂）
  const listeners = []
  const pauseWebsite = () => {
    if (isNative() || !document.hidden || !playing) return
    playing = false
    $('[data-w="toggle"]', panel).innerHTML = icon('play')
    $('.walk-next', panel).textContent = '模擬已暫停，回來後按播放繼續'
    try { speechSynthesis.cancel() } catch {}
  }
  document.addEventListener('visibilitychange', pauseWebsite)
  async function onBackground() {
    if (!playing || dist >= total || handoff || guardianState.running) return // 已有實際守護在跑就不搶
    const base = dist
    const rest = [
      positionAt(ROUTE.points, cum, base),
      ...ROUTE.points.filter((_, i) => cum[i] > base),
    ]
    if (rest.length < 2) return
    handoff = { base }
    handing = handoffWalk({
      points: rest,
      speed: (transport.kmh / 3.6) * speed,
      mode: transport.routeMode,
      hotspots: hotspots.filter((h) => h.along_m >= base - 10),
      skip: [...alerted],
    }).catch(() => {
      handoff = null
    })
    await handing
  }
  async function onForeground() {
    if (!handoff) return
    await handing
    const h = handoff
    handoff = null
    if (!h) return
    let moved = null
    try {
      moved = await takeBackWalk()
    } catch {
      moved = 0
    }
    dist = moved === null ? total : Math.min(total, h.base + moved)
    hotspots.forEach((x) => {
      if (x.along_m < dist) alerted.add(x.id)
    }) // 背景已經提醒過
    last = performance.now()
    if (dist >= total) {
      marker.setLatLng(ROUTE.points.at(-1))
      $('.walk-next', panel).textContent = `已抵達 ${ROUTE.end.name}`
      $('.walk-prog', panel).style.width = '100%'
      playing = false
      $('[data-w="toggle"]', panel).innerHTML = icon('refresh')
    }
  }
  if (isNative()) {
    CapApp.addListener('pause', onBackground)
      .then((l) => listeners.push(l))
      .catch(() => {})
    CapApp.addListener('resume', onForeground)
      .then((l) => listeners.push(l))
      .catch(() => {})
  }

  function stop() {
    document.removeEventListener('visibilitychange', pauseWebsite)
    listeners.forEach((l) => l.remove())
    if (handoff) {
      handoff = null
      takeBackWalk().catch(() => {})
    }
    panel.remove()
    frame?.remove()
    map.removeLayer(marker)
    clearTimeout(alertTimer)
    try {
      speechSynthesis?.cancel()
    } catch {
      /* ignore */
    }
    if (isNative()) TextToSpeech.stop().catch(() => {})
    onStop?.()
  }
  return { stop }
}
