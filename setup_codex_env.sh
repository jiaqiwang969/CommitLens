#!/bin/bash
# setup_codex_env.sh - 设置 CODEX 环境变量

# 尝试从多个来源获取 API key
API_KEY=""

# 1. 从 .cache/codex_api_key 文件读取
if [ -f ".cache/codex_api_key" ]; then
    API_KEY=$(cat .cache/codex_api_key | tr -d '\n' | tr -d '\r')
    echo "✅ 从 .cache/codex_api_key 读取 API key"
fi

# 2. 从 .env 文件读取
if [ -z "$API_KEY" ] && [ -f ".env" ]; then
    source .env
    if [ ! -z "$CODEX_API_KEY" ]; then
        API_KEY="$CODEX_API_KEY"
        echo "✅ 从 .env 文件读取 API key"
    fi
fi

# 3. 检查环境变量是否已设置
if [ -z "$API_KEY" ] && [ ! -z "$CODEX_API_KEY" ]; then
    API_KEY="$CODEX_API_KEY"
    echo "✅ 使用已存在的环境变量 CODEX_API_KEY"
fi

# 设置环境变量
if [ ! -z "$API_KEY" ]; then
    export CODEX_API_KEY="$API_KEY"
    echo "✅ CODEX_API_KEY 已设置"
    echo "   前4个字符: ${API_KEY:0:4}..."
else
    echo "❌ 未找到 API key！"
    echo "请通过以下方式之一设置："
    echo "1) echo 'your-key' > .cache/codex_api_key"
    echo "2) 在 .env 文件中添加: CODEX_API_KEY=your-key"
    echo "3) export CODEX_API_KEY='your-key'"
    exit 1
fi

# 如果提供了命令参数，执行命令
if [ $# -gt 0 ]; then
    echo "执行命令: $@"
    exec "$@"
fi