#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试连续滚动详情视图 - 验证点击列表项可以跳转到对应位置"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from datetime import datetime, timedelta
import time

# 创建测试目录
test_dir = Path(".test_continuous_scroll")
test_dir.mkdir(exist_ok=True)

# 创建包含多条消息的 codex_output.txt
output_file = test_dir / "codex_output.txt"

# 生成20条不同类型的消息以测试滚动
messages = []
base_time = datetime.now()

for i in range(20):
    timestamp = (base_time + timedelta(minutes=i)).strftime('%Y-%m-%dT%H:%M:%S')

    if i == 0:
        messages.append(f"[{timestamp}] OpenAI Codex v0.34.0")
        messages.append("--------")
    elif i % 5 == 1:
        messages.append(f"[{timestamp}] User instructions:")
        messages.append(f"执行任务 #{i}: 这是用户的第{i}条指令")
        messages.append("")
    elif i % 5 == 2:
        messages.append(f"[{timestamp}] thinking")
        messages.append("")
        messages.append(f"**思考任务 #{i}**")
        messages.append("")
        messages.append(f"这是AI的思考过程，包含了对任务{i}的分析。")
        messages.append(f"- 步骤1: 理解需求")
        messages.append(f"- 步骤2: 制定计划")
        messages.append(f"- 步骤3: 执行方案")
        messages.append("")
    elif i % 5 == 3:
        messages.append(f"[{timestamp}] codex")
        messages.append(f"这是Codex输出 #{i}。真正的代码输出内容，没有markdown格式。")
        messages.append(f"print('任务{i}执行完成')")
        messages.append("")
    elif i % 5 == 4:
        messages.append(f"[{timestamp}] exec echo \"Task {i}\"")
        messages.append(f"Task {i}")
        messages.append("")
        messages.append(f"[{timestamp}] exec echo \"Task {i}\" succeeded in {100+i*10}ms:")
        messages.append(f"Task {i} completed successfully")
        messages.append("")
    else:
        messages.append(f"[{timestamp}] tokens used: {1000 + i * 50}")
        messages.append("")

# 写入文件
output_content = "\n".join(messages)
output_file.write_text(output_content, encoding="utf-8")

# 创建状态文件
status_file = test_dir / "codex_status.txt"
status_file.write_text("0", encoding="utf-8")

print("=" * 60)
print("连续滚动测试环境已创建")
print("=" * 60)
print(f"\n目录: {test_dir.absolute()}")
print(f"文件: {output_file.name}")
print(f"消息数: 约20条不同类型的消息")

print("\n📝 测试步骤:")
print("1. 运行 GUI: python tools/sboxgen_gui.py")
print("2. 切换到 'Codex Output' 标签页")
print("3. 在目录选择中输入: " + str(test_dir.absolute()))
print("4. 点击 '加载' 按钮")

print("\n🎯 测试要点:")
print("✅ 消息详情应该显示所有消息（连续滚动）")
print("✅ 每条消息之间有分隔线")
print("✅ 点击列表中的消息，详情区应该滚动到对应位置")
print("✅ 选中的消息应该有黄色高亮背景")
print("✅ 可以通过滚动查看之前和之后的消息")

print("\n🔍 具体测试:")
print("1. 点击第1条消息 -> 应该跳到顶部")
print("2. 点击第10条消息 -> 应该跳到中间")
print("3. 点击第20条消息 -> 应该跳到底部")
print("4. 在详情区滚动 -> 应该能看到所有消息连续显示")
print("5. 关闭'自动跟踪最新' -> 新消息不会自动跳转")

print("\n💡 预期效果:")
print("- 所有消息在详情区连续显示（不是单独显示）")
print("- 点击列表项能准确跳转到对应消息")
print("- 高亮显示当前选中的消息")
print("- 可以自由滚动查看上下文")