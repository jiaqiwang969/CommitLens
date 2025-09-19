#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试时间显示格式优化"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from datetime import datetime, timedelta

# 创建测试目录
test_dir = Path(".test_timestamp")
test_dir.mkdir(exist_ok=True)

# 创建测试文件，包含不同时间的消息
output_file = test_dir / "codex_output.txt"
messages = []

# 生成一天内不同时间的消息
base_time = datetime.now()
times = [
    base_time - timedelta(hours=5, minutes=30),  # 5小时30分钟前
    base_time - timedelta(hours=2, minutes=15),  # 2小时15分钟前
    base_time - timedelta(hours=1, minutes=45),  # 1小时45分钟前
    base_time - timedelta(minutes=30),           # 30分钟前
    base_time - timedelta(minutes=10),           # 10分钟前
    base_time - timedelta(minutes=5),            # 5分钟前
    base_time,                                   # 现在
]

for i, t in enumerate(times, 1):
    timestamp = t.strftime('%Y-%m-%dT%H:%M:%S')
    messages.append(f"[{timestamp}] User instructions:")
    messages.append(f"任务 #{i} - 时间: {t.strftime('%H:%M:%S')}")
    messages.append("")
    messages.append(f"[{timestamp}] thinking")
    messages.append(f"思考任务 #{i}...")
    messages.append("")
    messages.append(f"[{timestamp}] codex")
    messages.append(f"执行任务 #{i}")
    messages.append("")
    messages.append(f"[{timestamp}] exec echo 'Task {i}'")
    messages.append(f"Task {i} completed")
    messages.append("")
    messages.append("--------")

output_file.write_text("\n".join(messages), encoding="utf-8")

print("=" * 70)
print("⏰ 时间显示格式优化测试")
print("=" * 70)

print("\n📋 改进前后对比：")
print("")
print("❌ 之前：[2025-09-] 用户指令    (只显示年月，信息量少)")
print("✅ 现在：[16:24:10] 用户指令    (显示具体时间，信息量大)")

print("\n🎯 测试内容：")
print(f"目录：{test_dir.absolute()}")
print("包含7条不同时间的消息，跨度5小时")

print("\n预期效果：")
print("┌──────────────────────────────────────┐")
print("│ 消息列表                              │")
print("├──────────────────────────────────────┤")

# 显示预期的列表项
for i, t in enumerate(times, 1):
    time_str = t.strftime('%H:%M:%S')
    print(f"│ 👤 [{time_str}] 用户指令           │")
    print(f"│ 🤔 [{time_str}] AI 思考            │")
    print(f"│ 🤖 [{time_str}] Codex 输出         │")
    print(f"│ ⚡ [{time_str}] 执行命令           │")
    if i < len(times):
        print("│ ━ ---                                │")

print("└──────────────────────────────────────┘")

print("\n✅ 优势：")
print("1. 时间信息更有用 - 快速判断消息的新旧")
print("2. 节省空间 - 去掉冗余的日期部分")
print("3. 更易阅读 - 关注点在时间，不是日期")

print("\n请运行 GUI 查看实际效果：")
print("python tools/sboxgen_gui.py")