# 任务中断状态显示优化

## 功能说明

优化了停止执行后的任务状态显示，确保被中断的任务正确显示为"⏹️ 中断"状态。

## 实现内容

### 1. 停止时更新任务状态

```python
# 文件：tools/sboxgen_gui.py，行号：3727-3736
# 更新任务执行器状态，将当前任务标记为中断
if hasattr(self, 'current_task_id') and self.current_task_id:
    # 将当前任务标记为中断（返回码-1）
    self.task_executor.status["failed"][self.current_task_id] = -1
    self.task_executor.save_status()
    self._task_log(f"任务 {self.current_task_id} 已标记为中断", "warning")
```

### 2. 状态显示分类优化

```python
# 文件：tools/sboxgen_gui.py，行号：2975-2988
elif task_id in status["failed"]:
    error_code = status['failed'][task_id]
    if error_code == 124:
        status_text = "⏱️ 超时"
        tags = ("timeout",)
    elif error_code == -1 or error_code == -15:
        status_text = "⏹️ 中断"
        tags = ("interrupted",)  # 使用独立的interrupted标签
    elif error_code == 127:
        status_text = "❌ 命令未找到"
        tags = ("failed",)
    else:
        status_text = f"❌ 失败({error_code})"
        tags = ("failed",)
```

### 3. 独立的颜色配置

```python
# 文件：tools/sboxgen_gui.py，行号：3001-3007
self.task_tree.tag_configure("completed", foreground="#00b050")   # 深绿色 - 完成
self.task_tree.tag_configure("failed", foreground="#ff4444")      # 红色 - 失败
self.task_tree.tag_configure("interrupted", foreground="#ff8800")  # 橙色 - 中断/暂停
self.task_tree.tag_configure("timeout", foreground="#ff6600")     # 深橙色 - 超时
self.task_tree.tag_configure("running", foreground="#0066cc", font=("", 10, "bold"))  # 蓝色加粗
self.task_tree.tag_configure("current", foreground="#ff8800")     # 橙色
self.task_tree.tag_configure("pending", foreground="#888888")     # 灰色
```

## 状态显示对照表

| 状态码 | 显示图标 | 显示文字 | 颜色 | 含义 |
|--------|----------|----------|------|------|
| 0 | ✅ | 完成 | 深绿色 | 执行成功 |
| -1 | ⏹️ | 中断 | 橙色 | 用户手动停止 |
| -15 | ⏹️ | 中断 | 橙色 | SIGTERM信号终止 |
| 124 | ⏱️ | 超时 | 深橙色 | 执行超时 |
| 127 | ❌ | 命令未找到 | 红色 | codex命令错误 |
| 其他 | ❌ | 失败(代码) | 红色 | 其他错误 |

## 执行流程

1. **用户点击停止按钮**
   - 终止正在执行的进程
   - 更新codex_status.txt为"interrupted"

2. **更新任务状态**
   - 将current_task_id对应的任务标记为失败，错误码-1
   - 保存状态到task_status.json

3. **刷新任务列表**
   - 读取更新后的状态
   - 显示"⏹️ 中断"和橙色高亮

4. **UI反馈**
   - 状态栏显示"状态: ⏹️ 已停止"
   - 任务列表实时更新
   - 日志显示"任务已标记为中断"

## 用户体验提升

1. **清晰的视觉区分**
   - 中断任务使用橙色，区别于红色的失败
   - 图标"⏹️"直观表示停止/暂停状态

2. **状态一致性**
   - 任务列表与状态栏同步显示
   - 重启GUI后状态保持

3. **可恢复性**
   - 中断的任务可以重新执行
   - 不计入失败次数限制

## 测试验证

### 测试步骤
1. 执行一个任务
2. 在执行过程中点击"停止执行"
3. 观察任务列表中该任务的状态

### 预期结果
- 任务显示为"⏹️ 中断"（橙色）
- 状态栏显示"状态: ⏹️ 已停止"
- 日志显示"任务 xxx 已标记为中断"
- 重启GUI后状态保持

## 总结

通过完善的状态管理和视觉反馈，用户可以清楚地了解每个任务的执行状态，特别是区分主动中断和执行失败，提供了更好的任务管理体验。