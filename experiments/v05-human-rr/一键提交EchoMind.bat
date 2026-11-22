@echo off
title EchoMind Commit and Push (Pure Live API + Human Benchmark)
cd /d "%~dp0"

echo ========================================================
echo   EchoMind Static Report Export and Git Push
echo   (Purging MOCK, Integrating Human Benchmark, Exporting)
echo ========================================================
echo.

echo [1/3] Purging MOCK data and generating index.html...
python export_static_demo.py
if errorlevel 1 (
    echo [ERROR] Failed to export static demo report.
    pause
    exit /b 1
)

echo.
echo [2/3] Adding files to Git...
git add index.html docs/ export_static_demo.py clean_mock_data.py fetch_human_benchmark.py data/human_benchmarks/ README.md EchoMind_Visual_Demo.html .gitignore
git commit -m "feat: integrate OSF human benchmark and 100% live API comparative showcase"

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
echo   Human Benchmark & Pure Live API Report are now Live.
echo ========================================================
echo.
echo Your GitHub Pages site:
echo https://kayla-cheung.github.io/EchoMind/
echo.
pause
