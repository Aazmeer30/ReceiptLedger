@echo off
setlocal enabledelayedexpansion

title ReceiptLedger Backend Server

echo ============================================================
echo           ReceiptLedger - Backend Startup Runner
echo ============================================================
echo.

:: 1. Navigate to backend directory
set "ROOT_DIR=%~dp0"
if exist "%ROOT_DIR%backend" (
    cd /d "%ROOT_DIR%backend"
) else (
    cd /d "%ROOT_DIR%"
)

:: 2. Auto-detect Tesseract OCR
echo [*] Checking Tesseract OCR installation...
where tesseract >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%t in ('where tesseract') do (
        echo [OK] Tesseract found on PATH: %%t
        goto :tess_done
    )
)

if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    set "PATH=C:\Program Files\Tesseract-OCR;%PATH%"
    set "TESSDATA_PREFIX=C:\Program Files\Tesseract-OCR\tessdata"
    echo [OK] Added C:\Program Files\Tesseract-OCR to PATH.
    goto :tess_done
)

if exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" (
    set "PATH=C:\Program Files (x86)\Tesseract-OCR;%PATH%"
    set "TESSDATA_PREFIX=C:\Program Files (x86)\Tesseract-OCR\tessdata"
    echo [OK] Added C:\Program Files (x86)\Tesseract-OCR to PATH.
    goto :tess_done
)

echo [WARNING] Tesseract OCR not found in default paths.
echo           Ensure Tesseract 5 is installed for offline OCR fallback.

:tess_done
echo.

:: 3. Auto-detect Python Virtual Environment
echo [*] Checking Python environment...
set "PY_EXE="
if exist ".venv\Scripts\python.exe" (
    set "PY_EXE=.venv\Scripts\python.exe"
    echo [OK] Using virtual environment: %CD%\.venv
    goto :py_found
)
if exist "..\.venv\Scripts\python.exe" (
    set "PY_EXE=..\.venv\Scripts\python.exe"
    echo [OK] Using virtual environment: %ROOT_DIR%.venv
    goto :py_found
)
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_EXE=python"
    echo [OK] Using system Python.
    goto :py_found
)

echo [ERROR] No Python interpreter found!
echo         Please install Python 3.10+ or create a virtual environment (.venv).
pause
exit /b 1

:py_found
%PY_EXE% --version
echo.

:: 4. Detect Wi-Fi / Local Area Network IP for Mobile Connection
echo [*] Resolving LAN IP address for mobile app...
set "LAN_IP="
for /f "delims=" %%i in ('%PY_EXE% -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()" 2^>nul') do (
    set "LAN_IP=%%i"
)
if "%LAN_IP%"=="" (
    set "LAN_IP=127.0.0.1"
)
echo [OK] Local LAN IP: %LAN_IP%
echo.

:: 5. Check and release Port 8000 if occupied
echo [*] Checking port 8000 availability...
set "CONFLICT_PID="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING"') do (
    set "CONFLICT_PID=%%p"
)

if not "%CONFLICT_PID%"=="" (
    echo [!] Port 8000 is occupied by process PID %CONFLICT_PID%.
    echo     Terminating stale process to prevent WinError 10013...
    taskkill /F /PID %CONFLICT_PID% >nul 2>&1
    ping 127.0.0.1 -n 2 >nul
    echo [OK] Port 8000 released successfully.
) else (
    echo [OK] Port 8000 is free.
)
echo.

:: 6. Display Connection Information Banner
echo ============================================================
echo   ReceiptLedger Backend is starting!
echo.
echo   - Local Web UI / Docs  : http://localhost:8000/docs
echo   - Local API Health     : http://localhost:8000/api/v1/health
echo   - Web Dashboard API    : http://localhost:8000/api/v1/dashboard/overview
echo   - Mobile App Base URL  : http://%LAN_IP%:8000
echo.
echo   Press CTRL+C anytime to stop the server.
echo ============================================================
echo.

:: 7. Launch Uvicorn
%PY_EXE% -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Server exited with code %ERRORLEVEL%.
    pause
)
