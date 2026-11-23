# 有路安網頁版

手機、平板與電腦可使用同一個網頁。地圖、排行、路口報告和 AI 使用專案根目錄的共用後端。瀏覽器定位需要 HTTPS 或 localhost，且使用者需允許定位。

在 `web/` 執行：

```powershell
npm ci
npm run build
node --test tests/*.mjs
```

網站成品在 `web/dist/`，由後端服務。首次部署與外出連線請參考根目錄的 [README](../README.md) 及[外出連線說明](../docs/remote-access.md)。

若要跑瀏覽器測試，先用 `npx playwright install chromium webkit` 安裝測試瀏覽器，設定 `E2E_WEB_BASE_URL` 為自己測試環境的完整網站入口，再執行 `npx playwright test`。
