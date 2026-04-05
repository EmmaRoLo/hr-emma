@echo off
cd /d "%~dp0"
echo Starting HR Emma...

start "HR Emma Dashboard" cmd /k "py run.py --dashboard"
timeout /t 2 >nul
start "HR Emma Tunnel" cmd /k "ngrok.exe http 5050 --domain=kelvin-preliable-lennie.ngrok-free.dev"

echo.
echo Dashboard local:  http://localhost:5050
echo Dashboard public: https://kelvin-preliable-lennie.ngrok-free.dev
echo.
pause
