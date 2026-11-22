@echo off
chcp 65001 >nul
title EchoMind 静态成果报告打包器
cd /d "%~dp0"
echo.
echo ========================================================
echo   EchoMind 交互式成果展示网页一键打包器
echo ========================================================
echo.
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 系统中未找到 Python 命令，请确认已安装 Python 3.10+ 并加入 PATH。
    pause
    exit /b 1
)

python export_static_demo.py
if errorlevel 1 (
    echo.
    echo [错误] 导出失败，请检查上方报错信息。
    pause
    exit /b 1
)

echo.
echo [成功] 正在用浏览器打开生成的交互式报告...
start "" "%~dp0EchoMind_Visual_Demo.html"
echo.
pause
