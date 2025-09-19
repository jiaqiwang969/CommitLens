#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试解析修复 - 区分thinking和codex内容"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from datetime import datetime

# 创建测试目录和文件
test_dir = Path(".test_parsing")
test_dir.mkdir(exist_ok=True)

# 创建测试的 codex_output.txt，包含thinking和codex内容
output_file = test_dir / "codex_output.txt"
output_content = f"""[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] OpenAI Codex v0.34.0 (test)
--------
[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] User instructions:
请完成以下任务

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] thinking

**分析任务结构**

我需要首先理解用户的需求，这是一个关于代码生成的任务。让我分析一下具体要求：
1. 需要创建一个新的功能
2. 要考虑性能优化
3. 确保代码质量

**制定实施计划**

基于分析，我的计划是：
- 第一步：创建基础结构
- 第二步：实现核心功能
- 第三步：添加测试

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] codex
**创建基础文件结构**

首先，我将创建必要的目录和文件。这是实际的输出内容，但包含了markdown格式。

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] codex
现在开始实际的代码实现。这是真正的codex输出，没有markdown标题格式。

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] exec echo "Hello World"
[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] exec echo "Hello World" succeeded in 100ms:
Hello World

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] thinking

**评估执行结果**

命令执行成功了。现在我需要考虑下一步的操作。

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] codex
命令执行完成。所有任务已成功完成。

[{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}] tokens used: 1234
"""

output_file.write_text(output_content, encoding="utf-8")

# 创建状态文件
status_file = test_dir / "codex_status.txt"
status_file.write_text("0", encoding="utf-8")

print("测试文件已创建:")
print(f"  目录: {test_dir.absolute()}")
print(f"  文件: {output_file.name}")

print("\n测试解析修复:")
print("1. Thinking内容应该显示为'AI 思考'，包含 **标题** 格式")
print("2. Codex内容应该过滤掉包含 **标题** 的错误内容")
print("3. 真正的Codex输出（不含markdown）应该正常显示")

print("\n请打开GUI并:")
print("1. 切换到 'Codex Output' 标签页")
print("2. 在目录选择中输入: " + str(test_dir.absolute()))
print("3. 点击 '加载'")
print("4. 检查消息列表:")
print("   - 'AI 思考' 消息应包含 **分析任务结构** 和 **制定实施计划**")
print("   - 'Codex 输出' 不应该显示包含 **创建基础文件结构** 的内容")
print("   - 应该看到真正的Codex输出: '现在开始实际的代码实现...'")