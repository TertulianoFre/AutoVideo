@echo off
title AutoVideo
chcp 65001 >nul
cd /d "%~dp0"
call .venv\Scripts\activate

start "" cmd /c "timeout /t 4 >nul && start http://127.0.0.1:8080"

uvicorn backend.main:app --reload --port 8080
pause
