@echo off
chcp 65001 >nul
setlocal EnableExtensions

title AI 剧本创作工具 v6（画面时间轴 + 角色配音）

set "TOOL_DIR=c:\Users\Dreamy\Desktop\ai剧本\script-tool-v6"
set "PORT=8004"
set "URL=http://127.0.0.1:%PORT%"
set "HELPER=%~dp0wait_and_open.ps1"
set "PYPY=%TOOL_DIR%\venv\Scripts\python.exe"

cd /d "%TOOL_DIR%"

echo ==================================================
echo    AI 剧本创作工具 v6   时间轴 + 配音版
echo ==================================================
echo.
echo   访问地址 : %URL%
echo   工作目录 : %TOOL_DIR%
echo   新增功能 : 画面时间轴(时间戳编辑) + 角色配音(CosyVoice)
echo   数据目录 : v6 独立 storage（与 v5 分开，互不影响）
echo.
echo   请勿关闭本窗口，关闭即停止服务。
echo.

REM ---------- 检查 1：Python 环境（v6 用自己的虚拟环境，含配音依赖 dashscope）----------
if not exist "%PYPY%" (
    echo [错误] 找不到 v6 虚拟环境: %PYPY%
    echo [办法] 请先在 script-tool-v6 目录里执行下面两条命令建环境：
    echo        python -m venv venv
    echo        venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM ---------- 检查 2：辅助脚本是否存在 ----------
if not exist "%HELPER%" (
    echo [错误] 找不到辅助脚本 wait_and_open.ps1
    echo [原因] 该文件必须和本 bat 放在同一个文件夹里。
    echo.
    pause
    exit /b 1
)

REM ---------- 检查 3：端口是否已被占用 ----------
netstat -ano | findstr /c:":%PORT% " | findstr /c:"LISTENING" >nul
if not errorlevel 1 (
    echo [提示] 端口 %PORT% 已经在使用中，v6 服务可能已经在运行了。
    echo [动作] 直接为你打开浏览器，不重复启动。
    echo.
    start "" %URL%
    echo 如需重启服务，请先关闭之前启动的那个窗口。
    echo.
    pause
    exit /b 0
)

echo 正在启动服务，请稍候...
echo 服务就绪后会自动打开浏览器，不需要手动刷新。
echo.

REM ---------- 后台等待端口就绪，就绪后再打开浏览器 ----------
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%HELPER%" -Port %PORT% -TimeoutSec 90

REM ---------- 前台启动服务：关闭本窗口即停止服务 ----------
"%PYPY%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%

echo.
echo ==================================================
echo    服务已停止
echo ==================================================
echo.
echo 如果是刚启动就退出，通常是报错了。
echo 请把上方红色的英文错误信息截图发给助手排查。
echo.
pause
endlocal
