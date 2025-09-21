# GPT-5 Codex High Model Configuration

## 更新说明

已将所有 Codex 执行命令更新为使用 `gpt-5-codex-high` 模型。

## 修改内容

### 1. Codex Output Tab（Codex输出标签页）

**位置**: `_execute_codex_command()` 和 `_run_codex_command()`

**更新前**:
```bash
codex exec --skip-git-repo-check --sandbox workspace-write "<command>"
```

**更新后**:
```bash
codex exec --skip-git-repo-check --sandbox workspace-write --model gpt-5-codex-high "<command>"
```

### 2. Task Executor Tab（任务执行器标签页）

**位置**: `_execute_task_with_prompt()`

**更新前**:
```bash
codex exec --skip-git-repo-check --sandbox workspace-write "<prompt>"
```

**更新后**:
```bash
codex exec --skip-git-repo-check --sandbox workspace-write --model gpt-5-codex-high "<prompt>"
```

## 影响范围

1. **Codex Output 功能**
   - 执行用户输入的 Codex 命令时使用高级模型
   - UI显示的完整命令已更新

2. **任务执行器功能**
   - 批量执行任务时使用高级模型
   - 单个任务执行时使用高级模型

## 模型特点

`gpt-5-codex-high` 模型的优势：
- 更强的代码理解和生成能力
- 更好的上下文理解
- 更准确的任务执行
- 支持更复杂的编程任务

## 使用说明

无需额外配置，所有 Codex 执行都会自动使用新模型。如果需要切换回默认模型，可以删除 `--model gpt-5-codex-high` 参数。

## 测试验证

建议测试以下场景：
1. Codex Output 标签页执行简单命令
2. 任务执行器批量执行任务
3. 长时间运行的复杂任务
4. 错误处理和中断功能