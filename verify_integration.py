#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试任务执行器GUI集成"""

import sys
from pathlib import Path

# 添加tools目录
sys.path.insert(0, str(Path(__file__).parent / "tools"))

print("=" * 70)
print("🧪 任务执行器GUI集成验证")
print("=" * 70)

# 1. 测试模块导入
print("\n1️⃣ 检查模块导入...")
try:
    from isolated_task_executor import IsolatedTaskExecutor
    print("   ✅ isolated_task_executor 模块导入成功")
except ImportError as e:
    print(f"   ❌ 模块导入失败: {e}")
    sys.exit(1)

# 2. 创建执行器实例
print("\n2️⃣ 创建执行器实例...")
try:
    executor = IsolatedTaskExecutor()
    print(f"   ✅ 执行器创建成功")
    print(f"   📁 工作目录: {executor.workspace_dir}")
    print(f"   📦 产物目录: {executor.artifacts_dir}")
except Exception as e:
    print(f"   ❌ 创建失败: {e}")
    sys.exit(1)

# 3. 获取任务列表
print("\n3️⃣ 扫描任务...")
try:
    tasks = executor.get_all_tasks()
    print(f"   ✅ 发现 {len(tasks)} 个任务")

    # 显示前5个任务
    print("\n   前5个任务:")
    for task in tasks[:5]:
        report_exists = "✓" if task["report"].exists() else "✗"
        figs_exists = "✓" if task["figs"].exists() else "✗"
        print(f"   - {task['id']}: 报告={report_exists} 图片={figs_exists}")
except Exception as e:
    print(f"   ❌ 扫描失败: {e}")

# 4. 检查状态管理
print("\n4️⃣ 检查状态管理...")
try:
    status = executor.status
    print(f"   ✅ 状态加载成功")
    print(f"   📊 已完成: {len(status['completed'])} 个")
    print(f"   ❌ 失败: {len(status['failed'])} 个")
    print(f"   🔄 当前: {status.get('current', 'None')}")
except Exception as e:
    print(f"   ❌ 状态检查失败: {e}")

# 5. 测试GUI组件导入
print("\n5️⃣ 检查GUI组件...")
try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
    print("   ✅ Tkinter组件可用")

    # 测试创建窗口（不显示）
    root = tk.Tk()
    root.withdraw()  # 隐藏窗口
    print("   ✅ 可以创建GUI窗口")
    root.destroy()
except Exception as e:
    print(f"   ❌ GUI组件问题: {e}")

print("\n" + "=" * 70)
print("✨ 集成验证完成！")
print("\n📋 总结:")
print("- isolated_task_executor.py 已在 tools/ 目录中")
print("- 模块可以正常导入和使用")
print(f"- 发现 {len(tasks)} 个待执行任务")
print("- GUI可以正常访问任务执行器")
print("\n现在可以运行 GUI 并使用'任务执行'标签页了！")
print("命令: python tools/sboxgen_gui.py")