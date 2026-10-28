@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" scripts\server.py start
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\remote_access.py start
echo.
echo 外出連線準備中，私人位址會放在 run\手機外出連線.txt。
echo 電腦要保持開機、連網，且不要睡眠。
pause
exit /b 0
:failed
echo 伺服器啟動失敗，請查看上方訊息。
pause
