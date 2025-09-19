#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证任务执行器模块导入"""

import sys
from pathlib import Path

# 添加tools目录到路径
tools_path = Path(__file__).parent / "tools"
sys.path.insert(0, str(tools_path))

print("测试isolated_task_executor模块导入...")

try:
    from isolated_task_executor import IsolatedTaskExecutor
    print("✅ 模块导入成功！")

    # 创建执行器实例
    executor = IsolatedTaskExecutor()
    print(f"✅ 执行器实例创建成功")
    print(f"   工作目录: {executor.workspace_dir}")
    print(f"   产物目录: {executor.artifacts_dir}")

    # 获取任务列表
    tasks = executor.get_all_tasks()
    print(f"✅ 发现 {len(tasks)} 个任务")

except ImportError as e:
    print(f"❌ 模块导入失败: {e}")
except Exception as e:
    print(f"❌ 其他错误: {e}")