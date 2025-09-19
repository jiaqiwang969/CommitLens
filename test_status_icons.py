#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试状态图标显示"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from datetime import datetime

# 创建测试目录和文件
test_dir = Path(".test_codex_output")
test_dir.mkdir(exist_ok=True)

# 创建测试 codex_output.txt
output_file = test_dir / "codex_output.txt"
output_content = f"""[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] OpenAI Codex v0.34.0 (test)
--------
[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] User instructions:
Test command

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] thinking
Testing status icons...

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] codex
Starting execution...

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] exec echo "Hello World"
Hello World

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] exec echo "Done"
Done
"""

output_file.write_text(output_content, encoding="utf-8")

# 创建不同状态的文件用于测试
status_file = test_dir / "codex_status.txt"
error_file = test_dir / "codex_error.txt"

print("测试文件已创建:")
print(f"  目录: {test_dir.absolute()}")
print(f"  输出文件: {output_file.name}")
print(f"  状态文件: {status_file.name}")
print(f"  错误文件: {error_file.name}")

# 测试不同的状态
test_cases = [
    ("running", "🔄 运行中..."),
    ("0", "✅ 执行成功"),
    ("124", "⏱️ 执行超时"),
    ("127", "❌ 命令未找到"),
    ("1", "⚠️ 退出码 1"),
]

print("\n测试状态图标:")
for status, expected_text in test_cases:
    status_file.write_text(status, encoding="utf-8")
    print(f"  状态 '{status}' -> {expected_text}")

# 测试错误消息
error_content = "Error: Command not found\nPlease check your installation"
error_file.write_text(error_content, encoding="utf-8")
print(f"\n测试错误消息:\n  {error_content}")

print("\n请打开 GUI 并:")
print("1. 点击 'Codex Output' 标签页")
print("2. 在文件夹选择中浏览到: " + str(test_dir.absolute()))
print("3. 点击 '加载' 按钮")
print("4. 观察状态图标是否正确显示")
print("5. 测试自动跟踪功能：")
print("   - 启用 '自动跟踪最新'")
print("   - 点击历史消息")
print("   - 查看是否在新消息时自动跳转")