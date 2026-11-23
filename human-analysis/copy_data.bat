@echo off
chcp 65001 >nul
set "SRC=%~1"
if "%SRC%"=="" set "SRC=%CALM_RR_CSV%"
if "%SRC%"=="" (
  echo [EchoMind] Please pass the local path to rr.csv as an argument or set CALM_RR_CSV.
  echo Example: copy_data.bat "path\to\calm\rr.csv"
  pause
  exit /b 1
)
echo [EchoMind] Copying Calm Thinking raw CSV to data\raw\ ...
if not exist "data\raw" mkdir "data\raw"
copy "%SRC%" "data\raw\rr.csv"
echo.
echo [EchoMind] SHA-256 checksum:
powershell -NoProfile -Command "Get-FileHash data\raw\rr.csv -Algorithm SHA256 | Select-Object Path, Hash"
pause
