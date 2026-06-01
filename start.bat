@echo off
cd /d "%~dp0"

echo.
echo ============================================
echo   Mercari Japan Price Monitor
echo ============================================
echo.

:: find Python
set PY_EXE=

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set PY_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
    goto found
)

if exist "C:\Program Files\Python312\python.exe" (
    set PY_EXE=C:\Program Files\Python312\python.exe
    goto found
)

if exist "C:\Python312\python.exe" (
    set PY_EXE=C:\Python312\python.exe
    goto found
)

echo Python 3.12 not found!
echo Please install from https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during install
pause
exit /b 1

:found
echo Python: %PY_EXE%

echo.
echo [1/2] Installing dependencies...
"%PY_EXE%" -m pip install flask apscheduler requests httpx --quiet

echo [2/2] Starting server...
echo ============================================
echo   Open http://localhost:5000 in browser
echo   Close this window to stop the server
echo ============================================
echo.

set PYTHONIOENCODING=utf-8
"%PY_EXE%" app.py

pause
