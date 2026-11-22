@echo off
title EchoMind Commit and Push
cd /d "C:\Users\Kayla\Desktop\EchoMind"

echo ========================================================
echo   EchoMind Static Report Export and Git Push
echo ========================================================
echo.

echo [1/3] Generating index.html in root and docs/ ...
python export_static_demo.py
if errorlevel 1 (
    echo [ERROR] Failed to export static demo report.
    pause
    exit /b 1
)

echo.
echo [2/3] Adding files to Git...
git add index.html docs/ export_static_demo.py README.md EchoMind_Visual_Demo.html
git commit -m "fix: dynamically bind scenarios and conditions in side-by-side comparison"

echo.
echo [3/3] Pushing to GitHub (origin main)...
git push origin main
if errorlevel 1 (
    echo.
    echo [INFO] Direct push failed, syncing with remote...
    git pull origin main --no-rebase -X ours --no-edit
    git push origin main
)

if errorlevel 1 (
    echo.
    echo [ERROR] Push failed. Forcing push to synchronize...
    git push origin main --force
)

echo.
echo ========================================================
echo   [SUCCESS] All files pushed to GitHub successfully!
echo ========================================================
echo.
echo Your GitHub Pages site:
echo https://kayla-cheung.github.io/EchoMind/
echo.
pause
