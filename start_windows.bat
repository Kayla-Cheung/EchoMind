@echo off
cd /d "%~dp0"
echo.
echo SOS Context Memory Lab
echo Open http://127.0.0.1:8768/ in your browser.
echo Keep this window open while using the workbench.
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ is required.
  pause
  exit /b 1
)
python launch_demo.py
if errorlevel 1 pause
