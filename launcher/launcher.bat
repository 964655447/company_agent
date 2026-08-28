@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

if not exist "%~dp0launcher.py" (
    echo [ERROR] launcher.py not found next to this bat
    pause
    exit /b 1
)

:: 选择用来跑后端的 python：COMPANY_PYTHON 环境变量 > backend 下的 venv > 系统 python
set "PY="
if defined COMPANY_PYTHON set "PY=%COMPANY_PYTHON%"
if not defined PY if exist "%~dp0..\backend\venv\Scripts\python.exe" set "PY=%~dp0..\backend\venv\Scripts\python.exe"
if not defined PY if exist "%~dp0..\backend\.venv\Scripts\python.exe" set "PY=%~dp0..\backend\.venv\Scripts\python.exe"
if not defined PY set "PY=python"

echo Using python: %PY%
echo Starting launcher... (close this window to stop the panel; backend keeps running)
echo Dashboard: http://localhost:9000/
"%PY%" "%~dp0launcher.py"
echo.
echo Launcher stopped.
pause
