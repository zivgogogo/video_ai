#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# 首次运行：从模板创建 .env
if [ ! -f .env ]; then
    echo ">>> 首次运行：创建 .env 配置文件"
    cp .env.example .env
    echo ">>> 请编辑 .env 文件，填入你的 AI API Key，然后重新运行此脚本"
    exit 1
fi

# Git Bash / WSL：将 SQLite 数据库指向 Windows 本机路径，避免跨文件系统锁问题
if grep -qiE 'mingw|microsoft' /proc/version 2>/dev/null; then
    export SCRIPT_TOOL_DATABASE_URL="sqlite:///C:/Users/${USERNAME}/script_tool.db"
    echo ">>> 检测到跨文件系统环境，数据库路径: ${SCRIPT_TOOL_DATABASE_URL}"
fi

# 安装依赖（如果需要）
if ! python.exe -c "import fastapi" 2>/dev/null; then
    echo ">>> 安装依赖..."
    pip.exe install -r requirements.txt
fi

echo ">>> 启动服务..."
echo ">>> 打开浏览器访问 http://localhost:8000"
python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
