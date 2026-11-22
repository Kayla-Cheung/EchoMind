@echo off
chcp 65001 >nul
echo [EchoMind] 正在將 Calm Thinking 原始數據複製至 data\raw\ ...
if not exist "data\raw" mkdir "data\raw"
copy "C:\Users\Kayla\Documents\Codex\2026-10-28\referenced-chatgpt-conversation-this-is-an-3\work\open-benchmark-discovery-20261030\calm\rr.csv" "data\raw\rr.csv"
echo.
echo [EchoMind] 校驗 SHA-256 哈希值：
powershell -NoProfile -Command "Get-FileHash data\raw\rr.csv -Algorithm SHA256 | Select-Object Path, Hash"
echo.
echo 完成！可直接在 VS Code 中開啟本專案。
pause
