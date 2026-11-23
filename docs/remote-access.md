# Android App／通用網頁版外出連線

Android 可以安裝 APK。iPhone、平板、電腦及其他裝置可透過瀏覽器使用網頁版。

## 使用方式

1. 完成 README 的首次啟動，建立自己的資料庫並建置 `web/dist/`。
2. 在主機執行「啟動兩個版本.cmd」。它會檢查既有資料庫，啟用共用 HTTPS 入口，再從外網驗證 Android 資料與網頁。
3. Android 使用者把管理者提供的完整位址貼入 App 伺服器設定。網站使用者在瀏覽器開啟完整網址即可。這兩個位址可在本機 `run/` 取得，請私下分享。

網頁版提供地圖、排行、路口體檢、AI、家人路線與五種交通模擬。授予定位權限後，前景可以在接近危險路口時提醒。網頁進入背景或裝置鎖屏時會停止定位和模擬。

主機需持續開機、連網且不睡眠。一般start_server.bat只啟動區網服務，外出另開專用入口。這是Cloudflare Quick Tunnel開發測試通道，不是永久網域；重啟可能換網址，手機要使用最新完整位址。

## 存取範圍

- 本機8091入口轉送指定API到127.0.0.1:8092；不開放PostgreSQL。停止通道只處理本輪自己的API、入口與cloudflared子程序，不停止原API8000或資料庫。
- 只有正確隨機通行碼路徑才能進網站或API。網站只供應web/dist中的HTML、腳本、樣式、字型和圖示，不作任意檔案下載。
- 網站自動連相同來源，保留私密路徑；Android原生首次設定仍留白。網站的同來源請求可用，外部任意來源、後台與API文件仍不開放。
- IPA、私鑰、.env、舊原生更新檔均不供應；/updates/stable.json 回傳 410。已移除原生更新資料夾設定。
- 保留HTTPS驗證，不更改防毒、防火牆或電源設定，不記錄帶通行碼的存取URL。API每個來源每分鐘120次、請求256KiB／回傳4MiB上限。

## 工具來源

使用官方cloudflared 2026.10.5 Windows amd64，放在tools/cloudflared.exe（不進Git）：

[官方下載](https://github.com/cloudflare/cloudflared/releases/download/2026.10.5/cloudflared-windows-amd64.exe)

SHA256：db4e4c413612a0916f3e1679d3caaf376f94911952d163028fb726fb2e0516a9

先校驗再執行；啟動時再次檢查。更換工具版本須重新確認官方摘要。使用QUIC，沒有略過TLS驗證。

## 檢查與紀錄

```powershell
uv run python scripts/remote_access.py status
uv run python scripts/verify_remote.py
uv run python scripts/remote_access.py stop
```

status檢查本機入口，不把舊狀態檔當目前連線證明；外網由verify_remote另行驗證。故障日誌在logs/remote-supervisor.log、remote-api.log、remote-gateway.log及remote-tunnel.log。不要把私人URL或通行碼貼到公開issue。

測試：tests/test_web_delivery.py驗證網站入口、檔案白名單、舊下載拒絕及同源API；web/e2e/website.spec.js 用桌面 Chrome、Android Chrome 和 iPhone WebKit 模擬驗證網站。瀏覽器測試不能取代實際手機，結果另記HANDOFF。
