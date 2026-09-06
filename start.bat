@echo off
setlocal
cd /d "%~dp0"
title SDVX B50 Bot

REM === stop any already-running bot instance (prevents duplicate Discord logins) ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_bot.ps1"

REM === use the project venv (create it on first run if missing) ===
if exist ".venv\Scripts\python.exe" goto :run

echo [start] No .venv found - creating virtualenv...
python -m venv .venv
if errorlevel 1 goto :setup_failed
echo [start] Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :setup_failed

:run
REM === make sure the bot token exists ===
if not exist ".env" (
    echo [start] No .env found - copying .env.example for you...
    copy /y ".env.example" ".env" >nul
    echo [start] Edit .env and set DISCORD_TOKEN, then run start.bat again.
    pause
    exit /b 1
)

echo [start] Starting bot (press Ctrl+C to stop)...
".venv\Scripts\python.exe" bot.py
echo [start] Bot exited with code %ERRORLEVEL%
pause
exit /b 0

:setup_failed
echo [start] Setup failed. Check that python is on PATH (3.14 recommended).
pause
exit /b 1
