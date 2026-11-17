@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" scripts\server.py start
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\remote_access.py start
if errorlevel 1 goto failed
echo 正在確認外出通道是否就緒…
".venv\Scripts\python.exe" scripts\remote_access.py wait
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\verify_remote.py
if errorlevel 1 goto failed
echo.
echo 外出連線已通過實際HTTPS資料庫查詢，手機請使用以下完整私人位址：
type "run\手機外出連線.txt"
echo.
echo 電腦要保持開機、連網，且不要睡眠。
pause
exit /b 0
:failed
echo 外出連線尚未完成，請查看上方訊息；不要沿用舊的連線網址。
pause
