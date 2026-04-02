@echo off
title Telegram Content Platform — Local Startup
color 0A

echo ============================================================
echo   Telegram Content Access Platform — Local Dev Startup
echo ============================================================
echo.

:: ── Conflict Guard ───────────────────────────────────────
:: Detect if platform processes are already running to prevent
:: duplicate bot instances (causes TelegramConflictError).
set "CONFLICT=0"
for /f "tokens=2" %%a in ('tasklist /FI "WINDOWTITLE eq Backend API" /NH 2^>nul ^| findstr /i "cmd.exe"') do set CONFLICT=1
for /f "tokens=2" %%a in ('tasklist /FI "WINDOWTITLE eq Telegram Gateway" /NH 2^>nul ^| findstr /i "cmd.exe"') do set CONFLICT=1
if "%CONFLICT%"=="1" (
    echo [WARNING] Platform processes are already running!
    echo           Running multiple instances causes TelegramConflictError.
    echo.
    choice /C YN /M "Kill existing processes and restart?"
    if errorlevel 2 (
        echo Aborted. Close existing windows manually or use Task Manager.
        pause
        exit /b 0
    )
    echo Stopping existing processes...
    taskkill /FI "WINDOWTITLE eq Backend API" /F >nul 2>&1
    taskkill /FI "WINDOWTITLE eq Telegram Gateway" /F >nul 2>&1
    taskkill /FI "WINDOWTITLE eq Workers" /F >nul 2>&1
    taskkill /FI "WINDOWTITLE eq Admin UI" /F >nul 2>&1
    timeout /t 2 /nobreak >nul
    echo [OK] Old processes killed.
    echo.
)

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

:: Create data directory for SQLite and logs
if not exist "data" mkdir data

:: Create .env from .env.example if not exists
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] Creating .env from .env.example ...
        copy .env.example .env >nul
        echo        Edit .env with your real values before production use.
    )
)

:: Create virtual environment if not exists
if not exist "venv" (
    echo [1/6] Creating virtual environment...
    python -m venv venv
) else (
    echo [1/6] Virtual environment exists.
)

:: Activate venv
call venv\Scripts\activate.bat

:: Install backend dependencies
echo [2/6] Installing Python dependencies...
pip install -r backend\requirements.txt -q
pip install -r telegram_gateway\requirements.txt -q

:: Install aiosqlite if not present (needed for SQLite dev mode)
pip install aiosqlite -q

:: Run the backend
echo.
echo [3/6] Starting FastAPI backend on http://localhost:8000 ...
echo       API docs: http://localhost:8000/docs
echo       Health:   http://localhost:8000/health
echo.

start "Backend API" cmd /k "call venv\Scripts\activate.bat && cd /d %~dp0 && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

:: Wait for backend to start before launching gateway
echo [4/6] Waiting for backend to start...
timeout /t 5 /nobreak >nul

:: Start Telegram Gateway (bot polling)
echo        Starting Telegram bot gateway...
start "Telegram Gateway" cmd /k "call venv\Scripts\activate.bat && cd /d %~dp0 && python -m telegram_gateway.bot_manager"

:: Check if Node.js is available for admin UI
echo [5/6] Checking admin UI...
node --version >nul 2>&1
if errorlevel 1 (
    echo [SKIP] Node.js not found — skipping admin UI.
    echo        Install Node.js 18+ from https://nodejs.org to enable admin panel.
) else (
    if not exist "admin_ui\node_modules" (
        echo        Installing admin UI dependencies...
        cd admin_ui && npm install && cd ..
    )
    echo        Starting admin UI on http://localhost:3000 ...
    start "Admin UI" cmd /k "cd /d %~dp0\admin_ui && npm run dev"
)

:: Check Redis for workers
echo [6/6] Checking Redis for workers...
redis-cli ping >nul 2>&1
if errorlevel 1 (
    echo [SKIP] Redis not running — workers will not start.
    echo        Install Redis from https://github.com/tporadowski/redis/releases
    echo        Or run without workers (API still works fully).
) else (
    echo        Starting background workers...
    start "Workers" cmd /k "call venv\Scripts\activate.bat && cd /d %~dp0 && python workers\main.py"
)

echo.
echo ============================================================
echo   Platform is starting!
echo.
echo   Backend API:      http://localhost:8000
echo   API Docs:         http://localhost:8000/docs
echo   Admin Panel:      http://localhost:3000  (if Node.js installed)
echo   Health Check:     http://localhost:8000/health
echo.
echo   Telegram Gateway: Running (polling mode)
echo   Logs:             data/backend.log, data/gateway.log
echo.
echo   Press any key to close this launcher (services keep running)
echo ============================================================
pause >nul
