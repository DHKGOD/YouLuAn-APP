@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please run uv sync first. See README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\dual_platform.py --workspace "%CD%" %*
exit /b %errorlevel%
