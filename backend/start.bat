@echo off
chcp 65001 >nul
title 公司管理智能体后端
cd /d %~dp0
echo 启动后端 http://localhost:8000 （前端同时托管，直接浏览器打开即可）
"***REMOVED***" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
