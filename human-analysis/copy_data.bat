@echo off
setlocal
if "%~1"=="" (
  echo Usage: copy_data.bat "C:\path\to\permitted\rr.csv"
  exit /b 2
)
python "%~dp0copy_data.py" "%~1"
exit /b %errorlevel%
