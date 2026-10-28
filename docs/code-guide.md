# 程式從哪裡開始看

有路安是用歷史事故資料提醒危險路口的 Android App。手機負責顯示地圖、取得位置和提醒；電腦上的 API 負責查資料庫和呼叫 AI 模型。手機不會直接連 PostgreSQL。

## 先看這三個流程

**查附近路口**：`frontend/src/views/ranking.js` 取得位置 → `api.js` 送出 `/api/hotspots/near` → `backend/app/routers/hotspots.py` 查詢 → PostgreSQL 回傳路口資料 → 畫面顯示清單。


**家人路線分享**：`family.js` 傳送路線至 `/api/routes` → `shared_route` 儲存 → 另一台裝置用六碼取得同一路線。

**背景守護**：`guardian.js` 呼叫 Android 外掛 → `GuardianPlugin.java` 啟動 `GuardianService.java` → 服務取得位置，交給 `GuardianEngine.java` 判斷是否接近路口 → 通知、語音或浮動提醒。網頁版沒有這項背景服務。

## 各部分負責什麼

| 位置 | 用途 |
|---|---|
| `frontend/src/main.js` | App 入口、切換分頁、返回上一頁、首次設定 |
| `frontend/src/views/` | 地圖、排行、報告、家人路線與設定畫面 |
| `frontend/src/api.js` | 儲存伺服器位址、傳送請求、處理逾時與錯誤 |
| `frontend/src/store.js` | 目前路線、天候、時段；通知畫面更新 |
| `frontend/src/ui.js` | 共用按鈕選單、彈出視窗、頁面堆疊與文字格式 |
| `frontend/src/map-utils.js` | 建立地圖、路口標記、路線，以及底圖斷線重試 |
| `frontend/src/walk.js` | 畫面中的模擬行走；切到背景時交給 Android 服務 |
| `frontend/src/guardian.js`、`alerts.js` | 連接原生守護服務、儲存與同步提醒設定 |
| `frontend/src/family.js`、`weather.js`、`export.js` | 常用路線與長輩模式、即時天氣、報告匯出 |
| `frontend/src/styles/`、`icons.js` | 樣式與圖示；SVG 路徑是圖形資料，不必逐字閱讀 |
| `backend/app/main.py`、`config.py`、`db.py` | API 入口、讀取設定、管理資料庫連線 |
| `backend/app/routers/` | 各功能的網址與處理流程；檔名對應功能 |
| `backend/app/filters.py`、`geo.py`、`advice.py` | 天候時段篩選、路線距離、規則式改善建議 |
| `frontend/android/.../guardian/` | 背景定位、提醒判斷、靈動島與護航小球 |
| `scripts/` | 下載、匯入、啟動、打包與測試工具 |
| `migrations/` | 建立資料表與索引，依檔名前的數字執行 |
| `ai/` | 訓練肇因模型、雨量校正及評估；不會在每次開 App 時重訓 |
| `tests/`、`frontend/e2e/` | 後端測試與瀏覽器操作測試 |

上表 Android 路徑省略的部分是 `app/src/main/java/tw/edu/fju/trafficsafety`。

## 資料怎麼進來

1. `scripts/download_data.py` 下載警政署原始資料。
2. `scripts/import_accidents.py` 清理欄位，將事故與當事人分開存。
3. `scripts/build_hotspots.py` 把位置接近的路口事故合併，產生 `hotspot`。
4. API 依座標、天候、時段或路線查詢，手機只取得這次需要的結果。

一件事故可能有多位當事人，所以 `party` 的列數不等於事故件數。筆數與資料表關係見 `db-report.md`、`er-diagram.md`。

## AI 做什麼

`ai/train_cause_model.py` 訓練肇因分類模型。App 選定情境後，`backend/app/routers/ai.py` 組合天候、時段、路口條件等特徵，回傳可能的肇因；預測結果與模型版本一起寫入資料庫。這不是預測下一秒一定會發生事故。

`ai/rain_risk.py` 另用測站實際雨量比較雨天事故，並和簡單基準比較。模型結果不一定比較好，實際數字保留在 `ai-report.md`、`ai-report-rain.md`，不要為了報告改數字。

## 閱讀時容易卡住的地方

- `lat` 是緯度，`lon` 是經度；Leaflet 部分介面用 `lng` 表示經度。
- `_m` 是公尺、`_s` 是秒、`_ms` 是毫秒。`along_m` 表示從路線起點累計的距離。
- SQL 的 `%(lat)s` 這類位置是參數，不是直接把使用者輸入拼成 SQL。
- `on(...)` 訂閱狀態變更，`emit(...)` 通知畫面；不是每個畫面各自保存一份路線。
- `try/catch` 有些是刻意保留備用方式，例如手機不支援震動時仍繼續顯示提醒。讀註解確認原因，不要直接刪掉。
- 守護預設距離為步行60、騎車120、開車220公尺；同一路口冷卻十分鐘。長輩模式與距離偏好會再調整。

## 修改後怎麼確認

後端跑 `uv run pytest`；前端跑 `npm run build` 和 `scripts/e2e.ps1`；Java 提醒邏輯跑 `scripts/test_guardian.ps1`。完整指令在 README。瀏覽器測試不能代替手機鎖屏後的 GPS、語音與浮動視窗測試。

`HANDOFF.md` 和 `TASKS.md` 是協作紀錄，保留當時做過的事及未完成項目。套件、打包產物、原始資料、模型檔及 Git 紀錄不需要改成另一種寫作風格。
