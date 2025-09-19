#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试追加模式 - 验证不覆盖输出文件"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from datetime import datetime, timedelta
import time

# 创建测试目录
test_dir = Path(".test_append_mode")
test_dir.mkdir(exist_ok=True)

# 创建初始的 codex_output.txt，包含一些历史内容
output_file = test_dir / "codex_output.txt"
initial_content = f"""[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] OpenAI Codex v0.34.0
--------
Previous Session History
--------
[{(datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')}] User instructions:
之前的任务

[{(datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')}] thinking
这是之前的思考内容

[{(datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')}] codex
这是之前的输出内容

[{(datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')}] exec echo "Previous task"
Previous task

--------
End of Previous Session
--------
"""

# 写入初始内容
output_file.write_text(initial_content, encoding="utf-8")

# 创建 error 和 status 文件
error_file = test_dir / "codex_error.txt"
status_file = test_dir / "codex_status.txt"

# 写入旧的错误和状态
error_file.write_text("Old error content", encoding="utf-8")
status_file.write_text("0", encoding="utf-8")

print("测试目录已创建:")
print(f"  目录: {test_dir.absolute()}")
print("")

# 显示初始文件内容
print("初始文件状态:")
print(f"  codex_output.txt: {len(output_file.read_text())} 字符")
print(f"  codex_error.txt: '{error_file.read_text()}'")
print(f"  codex_status.txt: '{status_file.read_text()}'")

print("\n测试场景:")
print("1. codex_output.txt 包含历史内容（不应被覆盖）")
print("2. codex_error.txt 包含旧错误（应被清空）")
print("3. codex_status.txt 包含旧状态（应被更新为'running'）")

print("\n测试步骤:")
print("1. 打开 GUI")
print("2. 切换到 'Codex Output' 标签页")
print("3. 在目录选择中输入: " + str(test_dir.absolute()))
print("4. 点击 '加载' - 应该看到历史内容")
print("5. 输入命令: echo 'New Command'")
print("6. 点击 '执行'")
print("7. 再次点击 '加载'")
print("")
print("预期结果:")
print("  ✅ codex_output.txt: 保留历史内容，新内容追加在后面")
print("  ✅ codex_error.txt: 被清空")
print("  ✅ codex_status.txt: 更新为 'running' 然后是执行结果")

# 模拟执行后的验证脚本
print("\n可以运行以下命令验证:")
print(f"  cat {output_file}  # 查看是否保留了历史内容")
print(f"  cat {error_file}   # 查看是否被清空")
print(f"  cat {status_file}  # 查看是否被更新")