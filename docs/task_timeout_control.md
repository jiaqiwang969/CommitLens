# 任务执行器超时控制功能完成

## 功能说明

已成功在任务执行器界面添加了可配置的超时控制，默认值设置为6000秒（100分钟）。

## 实现内容

### 1. UI界面更新
在任务执行器控制面板添加了超时设置输入框：

```python
# 文件：tools/sboxgen_gui.py，行号：2641-2643
ttk.Label(control_frame, text="超时(秒):").grid(row=3, column=0, sticky="w", pady=(5, 0))
self.task_timeout_var = tk.IntVar(value=6000)  # 默认6000秒
timeout_entry = ttk.Entry(control_frame, textvariable=self.task_timeout_var)
timeout_entry.grid(row=3, column=1, sticky="ew", padx=(5, 5), pady=(5, 0))
ttk.Label(control_frame, text="(默认6000秒)", foreground="#666", font=("", 9)).grid(row=3, column=2, sticky="w", padx=(5, 0), pady=(5, 0))
```

### 2. 执行逻辑更新
修改了任务执行方法以使用UI配置的超时时间：

```python
# 文件：tools/sboxgen_gui.py，行号：3906-3915
# 等待进程完成（使用UI配置的超时时间）
try:
    # 从 UI 控件获取超时时间（默认6000秒）
    timeout_seconds = self.task_timeout_var.get() if hasattr(self, 'task_timeout_var') else 6000
    self._task_log(f"🕑 设置执行超时时间: {timeout_seconds}秒", "info")
    return_code = process.wait(timeout=timeout_seconds)
except subprocess.TimeoutExpired:
    # 超时处理
    timeout_minutes = timeout_seconds // 60
    self._task_log(f"⚠️ 任务执行超过{timeout_minutes}分钟（{timeout_seconds}秒），正在终止...", "warning")
    if process.poll() is None:
        process.kill()
    return_code = 124
```

### 3. 设置持久化
超时设置会自动保存并在下次启动时恢复：

#### 保存设置
```python
# 文件：tools/sboxgen_gui.py，行号：447
"task_timeout": int(self.task_timeout_var.get()) if hasattr(self, 'task_timeout_var') else 6000,
```

#### 加载设置
```python
# 文件：tools/sboxgen_gui.py，行号：414-416
# Load task executor timeout setting (新增)
if hasattr(self, 'task_timeout_var'):
    self.task_timeout_var.set(int(data.get("task_timeout", 6000)))
```

## 用户界面变化

1. **控制面板新增超时设置**：
   - 位置：任务执行器标签页 > 控制面板
   - 显示：「超时(秒): [输入框] (默认6000秒)」
   - 位于"项目名称"下方，执行按钮上方

2. **执行日志提示**：
   - 任务开始时显示：「🕑 设置执行超时时间: 6000秒」
   - 超时时显示：「⚠️ 任务执行超过100分钟（6000秒），正在终止...」

## 使用说明

1. **默认超时**：6000秒（100分钟），适合长时间运行的GPT-5任务
2. **自定义超时**：在输入框中输入期望的超时秒数
3. **设置持久化**：设置会自动保存，下次启动时保持上次的设置
4. **超时行为**：超时后任务将被强制终止，返回码124

## 退出码说明

- `0`: 执行成功
- `124`: 执行超时（达到设置的超时时间）
- `-1`: 用户手动中断
- `-15`: SIGTERM信号终止
- 其他: 具体错误码

## 测试验证

✅ UI控件已添加到界面
✅ 默认值设置为6000秒
✅ 超时逻辑使用UI配置的值
✅ 设置可以保存和恢复
✅ 执行日志显示超时信息

## 优势

1. **灵活配置**：用户可根据任务需要自定义超时时间
2. **合理默认**：6000秒默认值适合GPT-5模型的长时间任务
3. **持久保存**：设置自动保存，避免重复配置
4. **清晰提示**：执行日志明确显示超时设置和状态
5. **向后兼容**：即使没有UI控件也有默认值保护