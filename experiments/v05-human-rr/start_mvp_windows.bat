@echo off
title EchoMind Memory Acquisition MVP - Offline
cd /d "%~dp0"
set ECHOMIND_OFFLINE=1
set ECHOMIND_PILOT_DB=%~dp0data\pilot.sqlite3
echo EchoMind Memory Acquisition MVP v0.2 - offline MOCK
echo Database: %ECHOMIND_PILOT_DB%
echo Open http://127.0.0.1:8769/#acquisition
python mvp_cli.py --serve --db "%ECHOMIND_PILOT_DB%" --port 8769
pause
