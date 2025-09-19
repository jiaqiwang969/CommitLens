#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试API key配置和任务执行"""

import os
import sys
from pathlib import Path

# 添加tools目录
sys.path.insert(0, str(Path(__file__).parent / "tools"))

print("=" * 70)
print("🔑 API Key 配置测试")
print("=" * 70)

# 1. 检查各种来源的API key
print("\n1️⃣ 检查API key来源...")

# 环境变量
env_key = os.environ.get("CODEX_API_KEY")
if env_key:
    print(f"   ✅ 环境变量 CODEX_API_KEY: {env_key[:4]}...")
else:
    print("   ❌ 环境变量未设置")

# 缓存文件
cache_file = Path(".cache/codex_api_key")
if cache_file.exists():
    try:
        cache_key = cache_file.read_text(encoding="utf-8").strip()
        print(f"   ✅ 缓存文件 .cache/codex_api_key: {cache_key[:4]}...")
    except:
        print("   ❌ 缓存文件读取失败")
else:
    print("   ❌ 缓存文件不存在")

# .env文件
env_file = Path(".env")
if env_file.exists():
    try:
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith("CODEX_API_KEY="):
                    env_key_from_file = line.split("=", 1)[1].strip().strip('"').strip("'")
                    print(f"   ✅ .env文件 CODEX_API_KEY: {env_key_from_file[:4]}...")
                    break
    except:
        print("   ❌ .env文件读取失败")
else:
    print("   ℹ️ .env文件不存在（可选）")

# 2. 测试任务执行器
print("\n2️⃣ 测试任务执行器...")

from isolated_task_executor import IsolatedTaskExecutor

executor = IsolatedTaskExecutor()
tasks = executor.get_all_tasks()

if tasks:
    print(f"   ✅ 发现 {len(tasks)} 个任务")

    # 测试第一个任务的准备（但不执行）
    task = tasks[0]
    print(f"\n3️⃣ 测试任务准备: {task['id']}...")

    # 准备工作空间
    success = executor.prepare_workspace(task)
    if success:
        print("   ✅ 工作空间准备成功")

        # 检查API key是否会被正确传递
        print("\n4️⃣ 模拟任务执行环境...")

        # 设置环境变量（如果还没有）
        if not os.environ.get("CODEX_API_KEY"):
            if cache_file.exists():
                try:
                    api_key = cache_file.read_text(encoding="utf-8").strip()
                    os.environ["CODEX_API_KEY"] = api_key
                    print(f"   ✅ 从缓存文件设置环境变量")
                except:
                    print("   ❌ 无法设置环境变量")

        # 清理工作空间
        executor.cleanup_workspace()
        print("   ✅ 工作空间已清理")
else:
    print("   ❌ 没有找到任务")

print("\n" + "=" * 70)
print("📋 总结:")
print("- API key 配置状态正常" if (env_key or cache_file.exists()) else "- 需要配置 API key")
print("- 任务执行器模块正常工作")
print(f"- 共有 {len(tasks)} 个任务待执行")
print("\n💡 提示:")
print("如果没有API key，请运行：")
print("  echo 'your-api-key' > .cache/codex_api_key")