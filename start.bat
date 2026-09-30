@echo off
REM SiliconRoute one-click start (Windows)
cd /d "%~dp0"
if not exist venv (
  echo Creating virtual environment...
  py -3.12 -m venv venv || (echo Python 3.12 not found. Install it from python.org & pause & exit /b 1)
)
call venv\Scripts\activate
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || (echo Install failed. & pause & exit /b 1)
if not exist "data\siliconroute.db" (
  if exist "data\final\siliconroute_final.db" (
    echo Seeding database from data\final\siliconroute_final.db...
    copy "data\final\siliconroute_final.db" "data\siliconroute.db" >nul
  )
)
REM open the browser 3 seconds after the server starts
start "" cmd /c "timeout /t 3 >nul && start http://127.0.0.1:8000"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
