// 匯出路口體檢報告：產生一份獨立的 HTML（可列印成 PDF）。
// App 內用 Capacitor Filesystem + Share 分享；網頁版直接下載。
import { Directory, Encoding, Filesystem } from '@capacitor/filesystem'
import { Share } from '@capacitor/share'
import { isNative } from './api.js'
import { esc } from './ui.js'

function bars(items, total) {
  const max = Math.max(1, ...items.map((item) => item.n))
  return items
    .map((item) => {
      const width = (item.n / max) * 100
      const percentage = Math.round((item.n / Math.max(1, total)) * 100)
      return `<tr><td>${esc(item.name)}</td><td class="bar"><span style="width:${width}%"></span></td><td class="n">${item.n}（${percentage}%）</td></tr>`
    })
    .join('')
}

export function reportHtml(report) {
  const hotspot = report.hotspot
  const summary = report.summary
  const hmax = Math.max(1, ...report.hourly)
  const vehicleTotal = report.vehicles.reduce((total, vehicle) => total + vehicle.n, 0)
  const now = new Date()
  return `<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>路口體檢報告－${esc(hotspot.name)}</title>
<style>
body{font-family:-apple-system,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif;color:#1c1c1e;max-width:780px;margin:24px auto;padding:0 20px;line-height:1.5}
h1{font-size:28px;margin:4px 0}h2{font-size:18px;margin:28px 0 10px;border-bottom:1px solid #e5e5ea;padding-bottom:6px}
.k{color:#8e8e93;font-size:13px;letter-spacing:.05em}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.s{background:#f2f2f7;border-radius:12px;padding:12px}.s b{font-size:24px;display:block}
table{width:100%;border-collapse:collapse;font-size:14px}td{padding:5px 4px}td.bar{width:45%}td.bar span{display:block;height:9px;border-radius:5px;background:#007aff}
td.n{text-align:right;color:#636366;white-space:nowrap}.hours{display:flex;align-items:flex-end;gap:2px;height:90px}.hours i{flex:1;background:#007aff99;border-radius:3px 3px 0 0}
li{margin:6px 0}.foot{margin-top:30px;font-size:12px;color:#8e8e93;border-top:1px solid #e5e5ea;padding-top:10px}
@media print{body{margin:0}}
</style></head><body>
<div class="k">路口體檢報告</div><h1>${esc(hotspot.name)}</h1>
<div>${esc([hotspot.city, hotspot.district].filter(Boolean).join(' '))}・座標 ${hotspot.lat.toFixed(
    5
  )}, ${hotspot.lon.toFixed(5)}・風險分數 ${hotspot.risk_score}</div>
<h2>摘要</h2><div class="grid">
<div class="s">事故<b>${summary.accidents} 件</b></div><div class="s">受傷<b>${summary.injuries} 人</b></div>
<div class="s">雨天占比<b>${Math.round(
    summary.rain_ratio * 100
  )}%</b></div><div class="s">夜間占比<b>${Math.round(summary.night_ratio * 100)}%</b></div></div>
<h2>時段分布（0–23 時）</h2><div class="hours">${report.hourly
    .map((n) => `<i style="height:${(n / hmax) * 100}%"></i>`)
    .join('')}</div>
<p>最常發生時段：${summary.peak_hour}:00–${summary.peak_hour + 1}:00</p>
<h2>主要肇因</h2><table>${bars(report.causes, summary.accidents)}</table>
<h2>事故型態</h2><table>${bars(report.collisions, summary.accidents)}</table>
<h2>涉入車種</h2><table>${bars(report.vehicles, vehicleTotal)}</table>
<h2>改善建議</h2><ul>${report.advice.road_user.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>
${
  report.advice.authority.length
    ? `<h3>給道路管理單位</h3><ul>${report.advice.authority
        .map((t) => `<li>${esc(t)}</li>`)
        .join('')}</ul>`
    : ''
}
<div class="foot">${esc(
    report.disclaimer
  )}。資料來源：內政部警政署即時交通事故資料(A2類) 115 年。產生時間：${now.toLocaleString(
    'zh-TW'
  )}</div>
</body></html>`
}

export async function exportReport(report) {
  const html = reportHtml(report)
  const fileName = `路口體檢報告_${report.hotspot.name.replace(/[\\/:*?"<>| ]+/g, '_')}.html`
  if (isNative()) {
    const fileResult = await Filesystem.writeFile({
      path: fileName,
      data: html,
      directory: Directory.Cache,
      encoding: Encoding.UTF8,
    })
    await Share.share({
      title: `路口體檢報告－${report.hotspot.name}`,
      url: fileResult.uri,
      dialogTitle: '匯出路口體檢報告',
    })
    return 'shared'
  }
  const downloadLink = document.createElement('a')
  downloadLink.href = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }))
  downloadLink.download = fileName
  downloadLink.click()
  setTimeout(() => URL.revokeObjectURL(downloadLink.href), 5000)
  return 'downloaded'
}
