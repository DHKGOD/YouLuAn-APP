// 後台：資料筆數、資料表關係、各月事故件數（證明資料都在資料庫裡）
import { api } from '../api.js'
import { icon } from '../icons.js'
import { $, esc, fmt, makePage } from '../ui.js'

const COLORS = {
  accident: 'var(--red)',
  party: 'var(--orange)',
  hotspot: 'var(--pink)',
  cause_code: 'var(--teal)',
  collision_type: 'var(--teal)',
  import_batch: 'var(--gray)',
  model_version: 'var(--indigo)',
  prediction: 'var(--indigo)',
}

export function adminView() {
  const page = makePage({ title: '後台', back: '設定' })
  page.body.innerHTML =
    '<div class="section"><div class="skeleton" style="height:300px;border-radius:14px"></div></div>'
  async function load() {
    try {
      const stats = await api('/api/admin/stats')
      const max = Math.max(1, ...stats.monthly.map((month) => month.n))
      const accidents = stats.tables.find((table) => table.table === 'accident').rows
      const party = stats.tables.find((table) => table.table === 'party').rows
      page.body.innerHTML = `
        <div class="section stat-grid">
          <div class="stat"><div class="stat-label" style="color:var(--red)">${icon(
            'car'
          )}事故件數</div><div class="stat-value">${fmt.n(accidents)}</div></div>
          <div class="stat"><div class="stat-label" style="color:var(--orange)">${icon(
            'person'
          )}當事人列數</div><div class="stat-value">${fmt.n(party)}</div></div>
        </div>
        <div class="section">
          <div class="section-header">資料表筆數（即時以 SQL count(*) 查詢）</div>
          <div class="list">${stats.tables
            .map(
              (table) => `
            <div class="cell" style="--sep-inset:58px">
              <span class="cell-icon" style="background:${COLORS[table.table] || 'var(--gray)'}">${icon(
                'database'
              )}</span>
              <span class="cell-main"><span class="cell-title" style="display:block">${esc(
                table.label
              )}</span><span class="cell-sub" style="display:block;font-family:ui-monospace,monospace">${esc(
                table.table
              )}</span></span>
              <span class="cell-value num">${fmt.n(table.rows)}</span>
            </div>`
            )
            .join('')}</div>
          <div class="section-footer">空間查詢：${
            stats.postgis ? 'PostGIS' : '一般 SQL（haversine）替代查詢'
          }</div>
        </div>
        <div class="section chart-card">
          <h4>${icon('chart')}各月事故件數</h4>
          <div class="bars" style="height:110px">${stats.monthly
            .map(
              (month, monthIndex) =>
                `<div class="bar" style="height:${(month.n / max) * 100}%;animation-delay:${
                  monthIndex * 40
                }ms" title="${month.label}：${month.n}"></div>`
            )
            .join('')}</div>
          <div class="bar-axis">${stats.monthly
            .map((month) => `<span>${month.label.split('/')[1]}</span>`)
            .join('')}</div>
        </div>
        <div class="section chart-card">
          <h4>${icon('layers')}資料表關係（外鍵）</h4>
          <div class="er">${stats.relations
            .map(
              (relation) => `
            <div class="er-row"><code>${esc(relation.child)}.${esc(
                relation.column
              )}</code><span class="arrow">${icon('chevronRight')}</span><code>${esc(
                relation.parent
              )}</code></div>`
            )
            .join('')}</div>
          <div class="hint" style="margin-top:12px">一件事故（accident）有多位當事人（party）；事故對應到危險路口（hotspot）、主要肇因（cause_code）與事故型態（collision_type）。</div>
        </div>
        <div class="section-footer">${esc(stats.data_source)}</div>`
    } catch (e) {
      page.body.innerHTML = `<div class="empty">${icon(
        'wifi'
      )}<div class="t-title3">讀取失敗</div><div>${esc(e.message)}</div></div>`
    }
  }
  return { el: page.el, onShow: load }
}
