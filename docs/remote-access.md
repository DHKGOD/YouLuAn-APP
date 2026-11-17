# Android App／iPhone網站外出連線

Android保留APK；iPhone自2026-11-17起只使用Safari網站，不提供IPA、SideStore安裝、原生背景守護或原生更新下載。

## 使用方式

1. 在主機執行「啟動外出連線.bat」。它會啟動資料庫、API和私密HTTPS通道，完成實際外網查詢驗證後才顯示位址。
2. Android把完整位址貼入App伺服器設定。iPhone在Safari直接開啟相同位址，結尾加「/」；不需要另外填伺服器設定、安裝描述檔、VPN或App。
3. 目前完整私人位址只在run/手機外出連線.txt及私有狀態檔，不預填APK，不提交Git，也不要公開。

iPhone可操作地圖、排行、路口體檢、AI、家人路線及模擬行走。網站模擬只在前景使用，切換程式或鎖屏會暫停；沒有跨App定位、懸浮視窗或鎖屏背景守護。

主機需持續開機、連網且不睡眠。一般start_server.bat只啟動區網服務，外出另開專用入口。這是Cloudflare Quick Tunnel開發測試通道，不是永久網域；重啟可能換網址，手機要使用最新完整位址。

## 存取範圍

- 本機8091入口轉送指定API到127.0.0.1:8092；不開放PostgreSQL。停止通道只處理本輪自己的API、入口與cloudflared子程序，不停止原API8000或資料庫。
- 只有正確隨機通行碼路徑才能進網站或API。網站只供應frontend/dist中的HTML、腳本、樣式、字型和圖示，不作任意檔案下載。
- 網站自動連相同來源，保留私密路徑；Android原生首次設定仍留白。網站的同來源請求可用，外部任意來源、後台與API文件仍不開放。
- IPA、私鑰、.env、舊原生更新檔均不供應；/updates/stable.json回410提示iPhone改用網站。已移除原生更新資料夾設定。
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

測試：tests/test_web_delivery.py驗證網站入口、檔案白名單、舊下載拒絕及同源API；frontend/e2e/ios-website.spec.js以WebKit驗證iPhone網站。瀏覽器測試不能取代實際手機，結果另記HANDOFF。
