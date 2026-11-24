@echo off
setlocal
set "ECHOMIND_AUDIT_SCRIPT=%~dp0repository\data_audit.py"
if not exist "%ECHOMIND_AUDIT_SCRIPT%" set "ECHOMIND_AUDIT_SCRIPT=%~dp0data_audit.py"
if not exist "%ECHOMIND_AUDIT_SCRIPT%" set "ECHOMIND_AUDIT_SCRIPT=%USERPROFILE%\Documents\ChatGPT\EchoMind\repository\data_audit.py"
if not exist "%ECHOMIND_AUDIT_SCRIPT%" goto missing
where python >nul 2>nul
if errorlevel 1 goto no_python
echo Starting EchoMind data review:
echo "%ECHOMIND_AUDIT_SCRIPT%"
python "%ECHOMIND_AUDIT_SCRIPT%" %*
set "ECHOMIND_AUDIT_EXIT=%ERRORLEVEL%"
if not "%~1"=="" exit /b %ECHOMIND_AUDIT_EXIT%
if not "%ECHOMIND_AUDIT_EXIT%"=="0" echo EchoMind exited with error %ECHOMIND_AUDIT_EXIT%.
pause
exit /b %ECHOMIND_AUDIT_EXIT%
:missing
echo EchoMind data_audit.py was not found. No Python command was started.
echo Open the canonical Documents\ChatGPT\EchoMind checkout and try again.
pause
exit /b 2
:no_python
echo Python is not available on PATH. Install Python 3.11 or enable its PATH entry.
pause
exit /b 3
