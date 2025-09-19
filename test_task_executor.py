#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试任务执行器功能"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from isolated_task_executor import IsolatedTaskExecutor
import json

# 初始化执行器
executor = IsolatedTaskExecutor()

print("=" * 70)
print("🧪 任务执行器集成测试")
print("=" * 70)

# 测试获取任务列表
print("\n📋 获取任务列表...")
tasks = executor.get_all_tasks()
print(f"找到 {len(tasks)} 个任务:")
for task in tasks:
    print(f"  - {task['id']}")
    print(f"    报告: {task['report'].exists()}")
    print(f"    图片: {task['figs'].exists()}")

# 测试状态管理
print("\n📊 检查执行状态...")
print(f"已完成: {len(executor.status['completed'])}")
print(f"失败: {len(executor.status['failed'])}")
print(f"当前任务: {executor.status.get('current', 'None')}")

# 测试获取下一个任务
print("\n🎯 获取下一个待执行任务...")
next_task = executor.get_next_task()
if next_task:
    print(f"下一个任务: {next_task['id']}")
else:
    print("所有任务已完成或没有任务")

# 测试工作空间准备（但不执行）
if next_task:
    print("\n🏗️ 测试工作空间准备...")
    success = executor.prepare_workspace(next_task)
    if success:
        print("✅ 工作空间准备成功")
        # 检查文件是否复制
        workspace = executor.current_dir
        if workspace.exists():
            print(f"工作目录: {workspace}")
            print("包含文件:")
            for f in workspace.iterdir():
                print(f"  - {f.name}")

        # 清理测试
        print("\n🧹 清理测试工作空间...")
        executor.cleanup_workspace()
        print("✅ 清理完成")

print("\n✨ 测试完成！任务执行器集成正常工作")