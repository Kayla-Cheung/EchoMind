# EchoMind Git Commit & Push Helper
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host ">>> [1/3] 正在生成静态报告..." -ForegroundColor Cyan
python export_static_demo.py

Write-Host ">>> [2/3] 正在执行 git commit..." -ForegroundColor Cyan
git add export_static_demo.py 打包演示网页.bat 一键提交到GitHub.bat push.ps1 README.md docs/ EchoMind_Visual_Demo.html
git commit -m "feat: add standalone visual demo and github pages export"

Write-Host ">>> [3/3] 正在推送至 GitHub (main)..." -ForegroundColor Cyan
git push origin main

Write-Host "`n>>> [成功] 提交与推送已完成！" -ForegroundColor Green
Write-Host "公开演示地址：https://kayla-cheung.github.io/EchoMind/" -ForegroundColor Yellow
