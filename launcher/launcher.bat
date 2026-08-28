@echo off
chcp 65001 >nul 2>&1
cd /d "***REMOVED***\launcher"

if not exist "***REMOVED***\launcher\launcher.py" (
    echo [ERROR] launcher.py not found in ***REMOVED***\launcher\
    pause
    exit /b 1
)

echo Starting launcher... (close this window to stop the panel; backend keeps running)
echo Dashboard: http://localhost:9000/
"***REMOVED***" "***REMOVED***\launcher\launcher.py"
echo.
echo Launcher stopped.
pause
