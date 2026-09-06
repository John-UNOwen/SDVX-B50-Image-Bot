@echo off
setlocal
cd /d "%~dp0"
title SDVX B50 Bot

REM === use the project venv (create it on first run if missing) ===
if exist ".venv\Scripts\python.exe" goto :env_ok
echo [start] No .venv found - creating virtualenv...
python -m venv .venv
if errorlevel 1 goto :setup_failed
echo [start] Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :setup_failed

:env_ok
REM === make sure the bot token exists ===
if not exist ".env" (
    echo [start] No .env found - copying .env.example for you...
    copy /y ".env.example" ".env" >nul
    echo [start] Edit .env and set DISCORD_TOKEN, then run start.bat again.
    pause
    exit /b 1
)

REM === single-instance launcher (stops old bots, prevents duplicate logins) ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_bot.ps1"
pause
exit /b 0

:setup_failed
echo [start] Setup failed. Check that python is on PATH (3.14 recommended).
pause
exit /b 1
