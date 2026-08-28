@echo off
chcp 65001 >nul 2>&1
title 公司管理智能体后端
cd /d "%~dp0"

echo 启动后端 http://localhost:8000 （前端同时托管，直接浏览器打开即可）
echo.

:: ---- 选择 Python ----
:: 禁止写死任何人的本机绝对路径，同事 clone 到任意目录都能直接双击运行。
:: 优先级：COMPANY_PYTHON 环境变量 > backend\venv > backend\.venv > py -3 > python
set "PY="
if defined COMPANY_PYTHON if exist "%COMPANY_PYTHON%" set "PY=%COMPANY_PYTHON%"
if defined PY goto :found_py
if exist "%~dp0venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"
if defined PY goto :found_py
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if defined PY goto :found_py
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto :found_py
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto :found_py

echo [错误] 未找到 Python。
echo 请安装 Python 3.10 及以上版本，或设置环境变量 COMPANY_PYTHON 指向 python.exe。
echo 例：setx COMPANY_PYTHON "D:\Python\python.exe"
echo.
pause
exit /b 1

:found_py
echo 使用 Python: %PY%

:: ---- 依赖自检（缺失则自动安装，避免同事看到一堆红色报错）----
%PY% -c "import uvicorn" >nul 2>nul
if not errorlevel 1 goto :run
echo.
echo [提示] 当前 Python 缺少依赖，正在安装 requirements.txt ...
%PY% -m pip install -r requirements.txt
if not errorlevel 1 goto :run
echo [错误] 依赖安装失败，请手动执行：
echo        %PY% -m pip install -r requirements.txt
echo.
pause
exit /b 1

:run
echo.
echo 后端启动中，接口文档：http://localhost:8000/docs
%PY% -m uvicorn app.main:app --host 0.0.0.0 --port 8000
echo.
echo 后端已停止。
pause
