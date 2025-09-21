# 停止执行按钮崩溃问题修复

## 问题描述

用户报告点击"停止执行"按钮后，程序直接崩溃退出。

## 根本原因

崩溃主要由以下几个原因导致：

1. **进程组权限问题**：尝试使用`os.killpg()`终止进程组时，可能因权限不足或进程组不存在而引发未捕获的异常

2. **进程状态检查不充分**：没有充分验证进程是否存在、是否有权限操作

3. **异常处理不完善**：关键操作缺少异常捕获，导致错误直接传播到主程序

4. **进程创建参数问题**：子进程创建时没有设置合适的会话参数

## 实施的修复

### 1. 增强异常处理（主要修复）

```python
# 文件：tools/sboxgen_gui.py，行号：3646-3740
def _stop_task_execution(self):
    """停止任务执行"""
    try:
        # 整个方法包装在try-except中
        self.task_executor_running = False

        # 安全检查属性是否存在
        if hasattr(self, 'current_task_id'):
            self.current_task_id = None

        if hasattr(self, 'task_monitoring'):
            self.task_monitoring = False

        # ... 进程终止逻辑 ...

    except Exception as e:
        # 捕获所有异常，避免程序崩溃
        self._task_log(f"停止执行时发生错误: {e}", "error")
        import traceback
        traceback.print_exc()
        # 确保重置状态
        self.task_executor_running = False
```

### 2. 改进进程终止策略

```python
# 采用渐进式终止策略
if os.name == "posix":
    try:
        # 1. 先尝试直接terminate
        self.task_exec_process.terminate()
        self._task_log("已发送终止信号", "info")

        # 2. 等待1秒
        try:
            self.task_exec_process.wait(timeout=1)
            self._task_log("进程已优雅终止", "success")
        except subprocess.TimeoutExpired:
            # 3. 如果还没退出，尝试发送到进程组
            try:
                pgid = os.getpgid(self.task_exec_process.pid)
                os.killpg(pgid, signal.SIGTERM)
                self._task_log("已发送终止信号到进程组", "info")
                self.task_exec_process.wait(timeout=1)
            except (ProcessLookupError, PermissionError, OSError) as e:
                # 4. 进程组操作失败，最后尝试强制kill
                self._task_log(f"无法终止进程组: {e}", "warning")
                try:
                    self.task_exec_process.kill()
                    self._task_log("进程已强制终止", "warning")
                except:
                    pass
    except (ProcessLookupError, PermissionError, OSError) as e:
        self._task_log(f"进程可能已经结束: {e}", "info")
```

### 3. 优化子进程创建

```python
# 文件：tools/sboxgen_gui.py，行号：3961-3976
# 在POSIX系统上创建新进程组，便于安全终止
kwargs = {
    "cwd": str(self.task_executor.workspace_dir),
    "stdout": subprocess.PIPE,
    "stderr": subprocess.PIPE,
    "text": True,
    "env": env,
    "bufsize": 1
}

# 在Unix系统上创建新会话
if os.name == "posix":
    kwargs["start_new_session"] = True

self.task_exec_process = subprocess.Popen(cmd, **kwargs)
```

### 4. 完善错误恢复

- 所有异常都被捕获并记录
- 状态变量确保被重置
- UI更新放在`root.after()`中延迟执行
- 添加详细的调试输出

## 关键改进点

### 1. 渐进式终止策略
```
尝试顺序：
1. process.terminate() → 温和终止
2. os.killpg() → 终止进程组
3. process.kill() → 强制终止
```

### 2. 异常捕获层级
```
外层 try-except：捕获所有异常
  ├─ 进程终止 try-except：处理进程操作异常
  ├─ 状态更新 try-except：处理文件操作异常
  └─ UI更新：确保执行
```

### 3. 进程创建优化
- 使用`start_new_session=True`创建新会话
- 便于进程组管理
- 隔离子进程，防止影响主程序

## 测试验证

### 测试场景

1. **正常停止**：任务执行中点击停止
2. **快速停止**：任务刚开始就停止
3. **重复停止**：多次点击停止按钮
4. **进程已结束**：进程已完成时点击停止

### 预期行为

- 不会崩溃退出
- 显示清晰的状态信息
- 进程被正确终止
- UI保持响应

### 错误处理输出示例

```
正在停止任务执行...
已发送终止信号
进程已优雅终止
任务执行已停止
状态: ⏹️ 已停止
```

或者在异常情况下：

```
正在停止任务执行...
已发送终止信号
无法终止进程组: [Errno 3] No such process
进程已强制终止
任务执行已停止
状态: ⏹️ 已停止
```

## 用户体验改善

1. **稳定性提升**：程序不会因停止操作崩溃
2. **状态反馈**：实时显示停止过程的每个步骤
3. **错误恢复**：即使出错也能恢复到正常状态
4. **日志记录**：详细记录终止过程便于调试

## 总结

通过完善的异常处理、渐进式终止策略和进程创建优化，彻底解决了停止执行按钮导致程序崩溃的问题。现在用户可以安全地在任何时候停止任务执行，而不用担心程序崩溃。