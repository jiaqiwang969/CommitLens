# 任务执行无限循环问题修复

## 问题描述

用户报告任务056-0451b70一直在循环执行，不断显示"准备任务 056-0451b70 的隔离环境..."，而不会继续执行下一个任务。

## 根本原因

问题出在任务状态管理的多个环节：

1. **路径更新触发状态重载**：`_refresh_task_list()`调用时会执行`set_workspace_dir()`，这会触发`_update_paths()`，从而重新加载状态文件，可能覆盖刚刚更新的内存状态。

2. **状态保存与加载的竞态条件**：任务完成后更新状态并保存，但刷新列表时立即重载状态，可能在文件还未完全写入时就读取了旧状态。

## 实施的修复

### 1. 优化路径更新逻辑

```python
# 文件：tools/isolated_task_executor.py，行号：39-45
def set_workspace_dir(self, workspace_dir):
    """更新工作目录并重新初始化相关路径"""
    new_dir = Path(workspace_dir)
    # 只有当路径真正改变时才更新
    if new_dir != self.workspace_dir:
        self.workspace_dir = new_dir
        self._update_paths()
```

**改进点**：
- 添加路径比较，避免不必要的状态重载
- 只在路径真正改变时才触发更新
- 防止相同路径的重复设置导致状态丢失

### 2. 增强调试输出

```python
# 文件：tools/isolated_task_executor.py，行号：82-100
def get_next_task(self):
    """获取下一个未完成的任务"""
    all_tasks = self.get_all_tasks()
    print(f"\n🔍 检查任务状态...")
    print(f"  已完成: {self.status['completed']}")
    print(f"  已失败: {list(self.status['failed'].keys())}")

    for task in all_tasks:
        if task["id"] not in self.status["completed"]:
            # 检查是否失败次数过多
            fail_count = self.status["failed"].get(task["id"], 0)
            if fail_count >= 3:
                print(f"  ⚠️ 任务 {task['id']} 失败{fail_count}次，跳过")
                continue
            print(f"  ➡️ 下一个任务: {task['id']} (失败{fail_count}次)")
            return task

    print(f"  ✅ 所有任务已完成")
    return None
```

### 3. 状态保存日志

```python
# 文件：tools/isolated_task_executor.py，行号：64-69
def save_status(self):
    """保存任务执行状态"""
    print(f"\n💾 保存状态到: {self.status_file}")
    print(f"  已完成: {self.status['completed']}")
    print(f"  已失败: {list(self.status['failed'].keys())}")
    self.status_file.write_text(json.dumps(self.status, indent=2))
```

## 问题解决机制

### 执行流程优化

1. **任务执行前**：
   - 检查路径是否真正改变
   - 避免不必要的状态重载
   - 保持内存状态的连续性

2. **任务执行中**：
   - 实时跟踪当前任务ID
   - 状态更新立即保存到文件
   - 详细的调试输出

3. **任务执行后**：
   - 确保状态已保存再刷新列表
   - 清除当前任务标记
   - 正确标记完成或失败

### 状态一致性保证

```
内存状态 → save_status() → 文件
     ↑                         ↓
     └──── load_status() ←─────┘
            (仅在路径改变时)
```

## 测试验证

### 测试步骤

1. 执行单个任务，观察是否正确完成并进入下一个
2. 批量执行任务，确认任务按序执行不重复
3. 中断执行后重启，验证状态正确恢复

### 预期行为

- 任务056执行一次后应标记为完成
- 下次执行应自动选择057任务
- 控制台输出显示清晰的状态转换

### 调试输出示例

```
🔍 检查任务状态...
  已完成: ['055-xxx', '056-0451b70']
  已失败: []
  ➡️ 下一个任务: 057-xxx (失败0次)

📦 准备任务 057-xxx 的隔离环境...

💾 保存状态到: .workspace/task_status.json
  已完成: ['055-xxx', '056-0451b70', '057-xxx']
  已失败: []
```

## 用户反馈处理

如果问题仍然存在，可通过以下方式诊断：

1. **检查状态文件**：
   ```bash
   cat .workspace/task_status.json
   ```

2. **观察调试输出**：
   - 查看"检查任务状态"输出
   - 确认任务ID是否正确添加到已完成列表

3. **手动重置**：
   - 使用"🗑️ 清空项目"按钮完全重置
   - 删除`.workspace/task_status.json`文件

## 总结

通过优化路径更新逻辑和避免不必要的状态重载，解决了任务无限循环的问题。增强的调试输出也有助于快速定位类似问题。