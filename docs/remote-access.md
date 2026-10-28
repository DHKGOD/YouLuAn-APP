# Android／iPhone 外出連線

電腦持續開機並連網時，可透過Cloudflare Quick Tunnel讓外面的 Android／iPhone App連回本機API，不必同Wi-Fi、不必改路由器，也不用重裝App。這是開發測試的臨時通道，不是永久網址或有服務保證的正式雲端部署。

## 使用方式

1. 首次準備好下方已驗證的cloudflared工具。
2. 執行「啟動外出連線.bat」，會啟動原伺服器與獨立通道。
3. 在本機讀取 run/手機外出連線.txt。
4. Android／iPhone App → 設定 → 伺服器位址，貼上**整段HTTPS位址，包含最後的通行碼** → 測試並儲存。
5. 關閉手機Wi-Fi，使用行動網路，確認連線、附近路口與報告正常。不要在駕駛時操作。

外出入口只提供App需要的API，不提供網頁版首頁。電腦要開機、連網且不睡眠；程式沒有修改Windows電源設定、安裝系統服務或開機排程。

## 存取限制

- 通道只連本機8091入口，再轉送指定API到獨立的127.0.0.1:8092；不直接開放PostgreSQL。
- 完整位址最後是隨機通行碼，沒有它就讀不到資料。通行碼存在自己的.env，位址在run/，都不進Git。
- 外出入口不提供後台統計、API文件、任意靜態檔案或私人設定。
- 保留HTTPS驗證，不關閉防毒、憑證驗證或防火牆；不記錄含通行碼的存取URL，不轉送Cookie或Authorization。
- 每個來源每分鐘最多120次請求，限制請求與回傳大小。這是共享憑證，不是每人獨立帳號；只把位址交給有權使用這些資料的人，不要貼到公開GitHub。

## 工具來源與校驗

本次使用Cloudflare官方cloudflared 2026.10.5（Windows amd64），下載到本專案 tools/cloudflared.exe，未安裝到系統。

[官方下載檔](https://github.com/cloudflare/cloudflared/releases/download/2026.10.5/cloudflared-windows-amd64.exe)的GitHub Release資產摘要SHA256：

```
db4e4c413612a0916f3e1679d3caaf376f94911952d163028fb726fb2e0516a9
```

先比對摘要再執行，啟動程式也會再次檢查；更換版本時須重新確認來源與摘要。本機HTTP/2通道曾遇憑證信任錯誤，改用官方支援的QUIC後建立連線，未放寬TLS驗證。

官方說明：[工具下載](https://developers.cloudflare.com/tunnel/downloads/)、[Quick Tunnel限制](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)。

## 停止與檢查

在專案根目錄執行：

```powershell
uv run python scripts/remote_access.py status
uv run python scripts/verify_remote.py
uv run python scripts/remote_access.py stop
```

stop只停止本輪建立的外出API、入口與通道，不停止原API或資料庫。重新建立Quick Tunnel會換網址，手機要貼新的完整位址；原通行碼仍保留。若通行碼外洩，先停止通道，再更新.env的REMOTE_ACCESS_KEY，並將新位址提供給允許使用的人。

## 故障紀錄

| 位置 | 內容 |
|---|---|
| logs/remote-supervisor.log | 啟動與停止原因 |
| logs/remote-gateway.log | 本機入口狀態；未開啟存取URL紀錄 |
| logs/remote-tunnel.log | Cloudflare連線狀態；不要切到會記錄請求內容的debug級別 |
| logs/remote-verification.json | 外部HTTPS、資料庫查詢與未授權拒絕結果，不含私人網址 |
| tests/test_remote_gateway.py | 用假後端驗證授權、路由、CORS、大小、限流與錯誤處理 |

電腦經公共HTTPS網址查詢成功，不等於手機4G/5G已實測；實機結果另記錄在HANDOFF。若要固定網址，需另外準備正式通道與網域或雲端主機，不能把Quick Tunnel當作永久方案。

## iPhone 畫面更新

iPhone 與 Android 使用同一個完整私密 API 位址。iPhone 原生版的更新下載只使用該位址的 HTTPS 網域，不含最後的通行碼。

若另有已簽署的 iPhone 更新資料夾，可在本機 `.env` 設定 `IOS_UPDATES_DIR` 指向該資料夾，再啟動外出模式。未設定時更新路由回 404；簽署私鑰不可放進該資料夾。

`/updates/stable.json` 與目前清單列出的更新檔可公開下載；不提供其他版本、任意檔案或 API 資料。iPhone App 仍會檢查內建公鑰、簽章、版本與逐檔雜湊。這只更新畫面，原生功能改動仍須新版 IPA。

外出模式建立自己專用的本機 API 程序，與原區網服務共用資料庫；停止時只處理自己建立的子程序。既有區網服務若尚未重啟，可能仍載入舊程式；不能把它當新版驗收結果。
