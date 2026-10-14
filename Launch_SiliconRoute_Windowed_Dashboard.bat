@echo off
title SiliconRoute Standalone Window
cd /d "%~dp0"

echo Ensuring SiliconRoute backend engine is active...
netstat -ano | findstr 127.0.0.1:8000 >nul
if %ERRORLEVEL% neq 0 (
    echo Starting SiliconRoute local engine...
    start /min "" "venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    timeout /t 3 /nobreak >nul
)

echo Launching SiliconRoute in Standalone Desktop Application Window...
start "" msedge.exe --app="http://127.0.0.1:8000/app/" --window-size=1440,920 --window-position=50,50
exit
