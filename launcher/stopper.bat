@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

if not exist "%~dp0stopper.py" (
    echo [ERROR] stopper.py not found next to this bat
    pause
    exit /b 1
)

:: 选择 python：COMPANY_PYTHON 环境变量 > backend 下的 venv > 系统 python
set "PY="
if defined COMPANY_PYTHON set "PY=%COMPANY_PYTHON%"
if not defined PY if exist "%~dp0..\backend\venv\Scripts\python.exe" set "PY=%~dp0..\backend\venv\Scripts\python.exe"
if not defined PY if exist "%~dp0..\backend\.venv\Scripts\python.exe" set "PY=%~dp0..\backend\.venv\Scripts\python.exe"
if not defined PY set "PY=python"

echo Using python: %PY%
echo Stopping all local services (backend 8000 + dashboard 9000)...
"%PY%" "%~dp0stopper.py"
