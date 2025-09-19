#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试真正的冻结模式 - 非自动跟踪时完全不更新显示"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from datetime import datetime
import time
import threading

# 创建测试目录
test_dir = Path(".test_freeze_mode")
test_dir.mkdir(exist_ok=True)

# 创建初始消息文件
output_file = test_dir / "codex_output.txt"
initial_messages = []

# 生成10条初始消息
for i in range(1, 11):
    timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    if i == 1:
        initial_messages.append(f"[{timestamp}] OpenAI Codex v0.34.0")
        initial_messages.append("--------")
    else:
        initial_messages.append(f"[{timestamp}] User instructions:")
        initial_messages.append(f"初始任务 #{i}")
        initial_messages.append("")
        initial_messages.append(f"[{timestamp}] codex")
        initial_messages.append(f"处理任务 #{i} 的输出")
        initial_messages.append("")

output_file.write_text("\n".join(initial_messages), encoding="utf-8")

print("=" * 80)
print("🧊 真正的冻结模式测试")
print("=" * 80)
print(f"\n测试目录: {test_dir.absolute()}")

print("\n📋 测试步骤:")
print("1. 运行 GUI: python tools/sboxgen_gui.py")
print("2. 切换到 'Codex Output' 标签页")
print("3. 在目录输入: " + str(test_dir.absolute()))
print("4. 点击 '加载' - 应该看到10条初始消息")
print("5. 点击 '开始监控'")

print("\n🎯 关键测试场景:")
print("")
print("场景1: 禁用自动跟踪后的完全冻结")
print("----------------------------------------")
print("1) 点击第1条消息（或任意历史消息）")
print("   → 自动跟踪自动禁用")
print("   → 显示: '[UI] 已暂停自动跟踪，正在查看历史消息'")
print("")
print("2) 等待新消息添加（下方会显示进度）")
print("   → 列表不更新")
print("   → 详情区不更新")
print("   → 只有状态栏显示: '消息数: N (有新消息)'")
print("")
print("3) 点击 '刷新' 按钮")
print("   → 新消息出现在列表中")
print("   → 保持当前选择不变")
print("")

print("场景2: 手动控制更新")
print("----------------------------------------")
print("1) 取消勾选 '自动跟踪最新'")
print("   → 显示: '[UI] 自动跟踪已禁用，显示已冻结。点击'刷新'按钮手动更新'")
print("")
print("2) 选择任意消息查看")
print("   → 完全不受新消息影响")
print("")
print("3) 需要时点击 '刷新'")
print("   → 手动加载新消息")
print("")

print("场景3: 恢复自动跟踪")
print("----------------------------------------")
print("1) 重新勾选 '自动跟踪最新'")
print("   → 立即刷新并跳到最新")
print("   → 恢复实时更新")
print("")

print("\n⚠️ 核心验证点:")
print("✅ 非自动跟踪时，显示完全静止")
print("✅ 新消息只在内存中解析，不刷新UI")
print("✅ 只有状态栏轻量提示有新消息")
print("✅ 用户完全控制何时更新")

print("\n📊 模拟消息生成（30秒）:")

def add_new_messages():
    """持续添加新消息"""
    for i in range(11, 26):  # 添加15条新消息
        time.sleep(2)
        timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        new_msg = f"""
[{timestamp}] User instructions:
新任务 #{i}

[{timestamp}] thinking
正在思考任务 #{i}...

[{timestamp}] codex
执行任务 #{i} 的结果

[{timestamp}] exec echo "Task {i}"
Task {i} output
"""
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write(new_msg)
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] 已添加消息 #{i} - 注意UI不应更新！")

# 启动模拟线程
thread = threading.Thread(target=add_new_messages, daemon=True)
thread.start()

print("\n测试运行中...")
print("请按上述步骤验证冻结模式的行为")

# 等待完成
try:
    thread.join()
    print("\n✅ 测试完成！")
    print("如果UI在禁用自动跟踪后完全静止，测试成功！")
except KeyboardInterrupt:
    print("\n测试已中断")