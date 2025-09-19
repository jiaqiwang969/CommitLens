#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试自动跟踪优化 - 验证取消自动跟踪后能稳定查看历史"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from datetime import datetime
import time
import threading
import subprocess

# 创建测试目录
test_dir = Path(".test_auto_follow")
test_dir.mkdir(exist_ok=True)

# 创建初始消息
output_file = test_dir / "codex_output.txt"
initial_messages = f"""[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] OpenAI Codex v0.34.0
--------
[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] User instructions:
Initial test task

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] thinking
Thinking about the task...

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] codex
Starting execution...
"""

output_file.write_text(initial_messages, encoding="utf-8")

print("=" * 70)
print("自动跟踪优化测试环境")
print("=" * 70)
print(f"\n测试目录: {test_dir.absolute()}")
print(f"输出文件: {output_file.name}")

print("\n📋 测试场景:")
print("测试取消自动跟踪后，即使有新消息也能稳定查看历史记录")

print("\n🎯 测试步骤:")
print("1. 运行 GUI: python tools/sboxgen_gui.py")
print("2. 切换到 'Codex Output' 标签页")
print("3. 在目录选择中输入: " + str(test_dir.absolute()))
print("4. 点击 '加载'")
print("5. 点击 '开始监控'")

print("\n📝 模拟持续更新:")

def append_messages():
    """模拟持续添加新消息"""
    for i in range(1, 21):
        time.sleep(2)  # 每2秒添加一条
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        new_msg = f"""
[{timestamp}] exec echo "Command {i}"
Command {i} output

[{timestamp}] exec echo "Command {i}" succeeded in {100+i*10}ms
"""
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write(new_msg)
        print(f"  已添加消息 #{i}")

# 启动后台线程持续添加消息
thread = threading.Thread(target=append_messages, daemon=True)
thread.start()

print("\n✅ 预期行为:")
print("1. 默认状态: '自动跟踪最新' 已启用")
print("   - 新消息自动显示在列表和详情区")
print("   - 自动滚动到最新位置")

print("\n2. 点击历史消息（如第1条）:")
print("   - 自动跟踪立即禁用")
print("   - 显示 '[UI] 已暂停自动跟踪，正在查看历史消息'")
print("   - 即使有新消息，选择和滚动位置保持不变")
print("   - 列表和详情区都停留在选中的历史消息")

print("\n3. 取消勾选 '自动跟踪最新':")
print("   - 显示 '[UI] 自动跟踪已禁用，可以自由查看历史消息'")
print("   - 可以自由滚动和选择任何消息")
print("   - 新消息不会干扰当前查看")

print("\n4. 重新勾选 '自动跟踪最新':")
print("   - 显示 '[UI] 自动跟踪已启用'")
print("   - 立即跳转到最新消息")
print("   - 恢复自动跟踪行为")

print("\n5. 点击最新消息:")
print("   - 如果之前禁用了自动跟踪，会重新启用")
print("   - 显示 '[UI] 已恢复自动跟踪最新消息'")

print("\n⚠️ 关键改进:")
print("- 用户查看历史时，界面完全稳定")
print("- 不会因新消息而跳转或改变选择")
print("- 清晰的状态提示，用户知道当前模式")
print("- 平滑的模式切换体验")

print("\n测试将持续40秒，每2秒添加一条新消息...")
print("请在此期间测试各种自动跟踪场景")

# 等待测试完成
try:
    thread.join()
except KeyboardInterrupt:
    print("\n测试已中断")

print("\n测试完成！")