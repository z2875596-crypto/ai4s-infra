@echo off
setlocal enabledelayedexpansion

echo.
echo  =============================================
echo    AI4S Infrastructure Platform
echo    Data - RLHF - Agent - HPC Fusion
echo  =============================================
echo.

set ROOT=%~dp0
set BACKEND_PORT=8000
set FRONTEND_PORT=3000

:: ---------- 1. Check Python --------------------------
echo  [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Please install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do echo         Python %%v [OK]

:: ---------- 2. Check Node.js -------------------------
echo  [2/5] Checking Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Node.js not found. Please install Node.js 18+ and add to PATH.
    pause
    exit /b 1
)
for /f "tokens=1 delims=v" %%v in ('node --version 2^>^&1') do echo         Node %%v [OK]

:: ---------- 3. Install Python deps -------------------
echo  [3/5] Installing Python dependencies...
cd /d "%ROOT%"
if not exist ".deps_installed" (
    pip install -e . >nul 2>&1
    if not errorlevel 1 (
        echo         Python deps [OK]
        type nul > .deps_installed
    ) else (
        echo  [WARN] pip install -e . had issues, trying minimal install...
        pip install fastapi uvicorn pydantic pyyaml prometheus-client httpx >nul 2>&1
        type nul > .deps_installed
        echo         Minimal Python deps [OK]
    )
) else (
    echo         Already installed [OK]
)

:: ---------- 4. Install Node deps ---------------------
echo  [4/5] Installing Node.js dependencies...
cd /d "%ROOT%frontend"
if not exist "node_modules" (
    call npm install
    echo         Frontend deps [OK]
) else (
    echo         Already installed [OK]
)
cd /d "%ROOT%"

:: ---------- 5. Launch services -----------------------
echo  [5/5] Starting services...
echo.

:: Kill any existing processes on our ports
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING" 2^>nul') do (
    taskkill /f /pid %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT% " ^| findstr "LISTENING" 2^>nul') do (
    taskkill /f /pid %%a >nul 2>&1
)

:: Launch backend in its own window
start "AI4S Backend :8000" /D "%ROOT%" cmd /c "python main.py 2>&1"
echo         Backend starting on http://localhost:%BACKEND_PORT% ...

:: Launch frontend in its own window
start "AI4S Frontend :3000" /D "%ROOT%frontend" cmd /c "npx vite --host 2>&1"
echo         Frontend starting on http://localhost:%FRONTEND_PORT% ...

:: ---------- Wait and open browser --------------------
echo.
echo  Waiting for servers to be ready...
echo.

:: Wait for backend
for /l %%i in (1,1,60) do (
    curl -s http://localhost:%BACKEND_PORT%/health >nul 2>&1
    if !errorlevel! equ 0 goto :backend_ready
    timeout /t 1 /nobreak >nul
)
:backend_ready
echo         Backend is live [OK]

:: Wait for frontend
for /l %%i in (1,1,30) do (
    curl -s http://localhost:%FRONTEND_PORT% >nul 2>&1
    if !errorlevel! equ 0 goto :frontend_ready
    timeout /t 1 /nobreak >nul
)
:frontend_ready
echo         Frontend is live [OK]

:: Open browser
echo.
echo  Opening http://localhost:%FRONTEND_PORT% ...
start "" http://localhost:%FRONTEND_PORT%

echo.
echo  =============================================
echo    All services running!
echo    Frontend : http://localhost:3000
echo    Backend  : http://localhost:8000
echo    API Docs : http://localhost:8000/docs
echo    Health   : http://localhost:8000/health
echo.
echo    Close the two terminal windows to stop.
echo  =============================================
echo.

pause
