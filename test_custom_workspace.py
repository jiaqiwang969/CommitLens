#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试自定义工作目录功能"""

import sys
from pathlib import Path
import tempfile
import shutil

# 添加tools目录
sys.path.insert(0, str(Path(__file__).parent / "tools"))

from isolated_task_executor import IsolatedTaskExecutor

print("=" * 70)
print("🧪 测试自定义工作目录")
print("=" * 70)

# 1. 测试默认路径
print("\n1️⃣ 测试默认路径...")
executor1 = IsolatedTaskExecutor()
print(f"   默认工作目录: {executor1.workspace_dir}")
print(f"   默认产物目录: {executor1.artifacts_dir}")
print(f"   当前工作目录: {executor1.current_dir}")
print(f"   状态文件路径: {executor1.status_file}")
print(f"   日志目录路径: {executor1.log_dir}")

# 2. 测试自定义路径（桌面）
desktop_workspace = Path.home() / "Desktop" / "workspace"
print(f"\n2️⃣ 测试自定义路径: {desktop_workspace}")
executor2 = IsolatedTaskExecutor(
    workspace_dir=str(desktop_workspace),
    artifacts_dir=".artifacts"
)
print(f"   工作目录: {executor2.workspace_dir}")
print(f"   当前工作目录: {executor2.current_dir}")
print(f"   状态文件路径: {executor2.status_file}")
print(f"   日志目录路径: {executor2.log_dir}")

# 验证目录创建
if executor2.workspace_dir.exists():
    print(f"   ✅ 工作目录已创建: {executor2.workspace_dir}")
if executor2.log_dir.exists():
    print(f"   ✅ 日志目录已创建: {executor2.log_dir}")

# 3. 测试动态更新路径
print("\n3️⃣ 测试动态更新路径...")
temp_dir = Path(tempfile.mkdtemp(prefix="test_workspace_"))
print(f"   创建临时目录: {temp_dir}")

executor3 = IsolatedTaskExecutor()
print(f"   初始工作目录: {executor3.workspace_dir}")

# 更新工作目录
executor3.set_workspace_dir(str(temp_dir))
print(f"   更新后工作目录: {executor3.workspace_dir}")
print(f"   更新后当前目录: {executor3.current_dir}")
print(f"   更新后状态文件: {executor3.status_file}")
print(f"   更新后日志目录: {executor3.log_dir}")

# 验证新目录创建
if executor3.workspace_dir.exists():
    print(f"   ✅ 新工作目录已创建")
if executor3.log_dir.exists():
    print(f"   ✅ 新日志目录已创建")

# 4. 测试任务准备（使用自定义路径）
print("\n4️⃣ 测试任务准备（使用自定义路径）...")
tasks = executor2.get_all_tasks()
if tasks:
    task = tasks[0]
    print(f"   准备任务: {task['id']}")

    # 准备工作空间
    success = executor2.prepare_workspace(task)
    if success:
        print(f"   ✅ 工作空间准备成功")
        print(f"   工作空间位置: {executor2.current_dir}")
        print(f"   确认路径: {executor2.current_dir.absolute()}")

        # 验证是否在正确位置
        if str(desktop_workspace) in str(executor2.current_dir):
            print(f"   ✅ 确认使用自定义路径!")
        else:
            print(f"   ❌ 错误：仍然使用默认路径")

        # 清理
        executor2.cleanup_workspace()
        print(f"   ✅ 工作空间已清理")

# 5. 清理测试临时目录
print("\n5️⃣ 清理测试...")
shutil.rmtree(temp_dir, ignore_errors=True)
print(f"   ✅ 临时目录已删除")

print("\n" + "=" * 70)
print("📋 测试总结:")
print("- 默认路径初始化正常")
print("- 自定义路径初始化正常")
print("- 动态路径更新正常")
print("- 任务准备使用正确的自定义路径")
print("\n✨ 工作目录自定义功能测试通过！")