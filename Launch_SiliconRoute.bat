@echo off
title SiliconRoute Desktop Application
echo Starting SiliconRoute Hardware AI Monitor and Load Balancer...
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    start "" "venv\Scripts\python.exe" "SiliconRoute_Desktop.py"
) else (
    start "" python "SiliconRoute_Desktop.py"
)
exit
