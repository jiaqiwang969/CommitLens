# API错误检测和状态判断修复

## 问题描述

用户发现当Codex API返回错误时（如"We're currently experiencing high demand"），程序仍然将任务标记为成功（返回码0），这是一个严重的误判问题。

## 根本原因

`codex`命令即使在遇到API错误时也返回退出码0，仅通过退出码无法判断执行是否真正成功。需要额外检查输出内容中的错误模式。

## 实施的修复

### 1. API错误模式检测

```python
# 文件：tools/sboxgen_gui.py，行号：4126-4150
# 检查输出中是否包含API错误或其他已知错误模式
api_error_detected = False
error_patterns = [
    "ERROR: We're currently experiencing high demand",
    "ERROR: Rate limit exceeded",
    "ERROR: API key is invalid",
    "ERROR: Unauthorized",
    "ERROR: Service unavailable",
    "ERROR:",  # 通用ERROR模式
    "stream error: We're currently experiencing high demand",
    "Authentication failed",
    "Permission denied"
]

# 检查输出中是否有错误模式
for pattern in error_patterns:
    if pattern in full_output:
        api_error_detected = True
        self._task_log(f"⚠️ 检测到API错误: {pattern[:50]}...", "error")
        # 如果检测到API错误，覆盖return_code
        if return_code == 0:
            return_code = 503  # Service Unavailable
            # 更新状态文件
            status_file.write_text("503", encoding="utf-8")
        break
```

### 2. 状态显示增强

```python
# 文件：tools/sboxgen_gui.py，行号：2975-2990
elif task_id in status["failed"]:
    error_code = status['failed'][task_id]
    if error_code == 124:
        status_text = "⏱️ 超时"
        tags = ("timeout",)
    elif error_code == -1 or error_code == -15:
        status_text = "⏹️ 中断"
        tags = ("interrupted",)
    elif error_code == 127:
        status_text = "❌ 命令未找到"
        tags = ("failed",)
    elif error_code == 503:
        status_text = "🚫 API错误"  # 新增API错误显示
        tags = ("api_error",)
    else:
        status_text = f"❌ 失败({error_code})"
        tags = ("failed",)
```

### 3. 颜色配置

```python
# 文件：tools/sboxgen_gui.py，行号：3007-3011
self.task_tree.tag_configure("api_error", foreground="#ff00ff")  # 紫色 - API错误
```

## 错误检测机制

### 检测流程

```
1. 执行codex命令
    ↓
2. 获取返回码
    ↓
3. 收集完整输出
    ↓
4. 扫描错误模式
    ↓
5. 如果返回码=0且检测到API错误
    → 覆盖为503
    ↓
6. 根据最终返回码判断成功/失败
```

### 错误模式列表

| 错误模式 | 含义 | 处理 |
|----------|------|------|
| ERROR: We're currently experiencing high demand | API过载 | 标记为503 |
| ERROR: Rate limit exceeded | 速率限制 | 标记为503 |
| ERROR: API key is invalid | 无效密钥 | 标记为503 |
| ERROR: Unauthorized | 未授权 | 标记为503 |
| stream error: | 流错误 | 标记为503 |
| Authentication failed | 认证失败 | 标记为503 |

## 状态码对照表

| 状态码 | 含义 | 显示 | 颜色 |
|--------|------|------|------|
| 0 | 成功 | ✅ 完成 | 绿色 |
| -1/-15 | 用户中断 | ⏹️ 中断 | 橙色 |
| 124 | 超时 | ⏱️ 超时 | 深橙色 |
| 127 | 命令未找到 | ❌ 命令未找到 | 红色 |
| 503 | API错误 | 🚫 API错误 | 紫色 |
| 其他 | 一般错误 | ❌ 失败 | 红色 |

## 测试用例

### 场景1：API过载错误

**输出内容**：
```
[2025-09-20T23:50:40] stream error: We're currently experiencing high demand, which may cause temporary errors.; retrying 1/5 in 188ms…
...
[2025-09-20T23:51:12] ERROR: We're currently experiencing high demand, which may cause temporary errors.
```

**期望结果**：
- 检测到API错误
- 返回码修改为503
- 任务标记为失败
- 显示"🚫 API错误"（紫色）

### 场景2：正常执行成功

**输出内容**：
```
[2025-09-20T23:50:34] User instructions:
...
[2025-09-20T23:51:12] Task completed successfully
```

**期望结果**：
- 未检测到错误
- 返回码保持0
- 任务标记为成功
- 显示"✅ 完成"（绿色）

## 用户体验改善

1. **准确的状态反馈**：API错误不再被误判为成功
2. **清晰的错误提示**：紫色"🚫 API错误"明确指示API问题
3. **可重试性**：API错误的任务可以重新执行
4. **日志记录**：错误模式被记录到日志便于调试

## 后续建议

1. **智能重试**：检测到API错误时可以自动延迟重试
2. **错误统计**：统计API错误频率，提示用户调整执行策略
3. **备用API**：支持配置备用API端点
4. **错误详情**：在UI中显示具体的错误信息

## 总结

通过在输出中检测错误模式并正确设置状态码，解决了API错误被误判为成功的问题。现在系统能够准确识别并报告API错误，为用户提供正确的执行状态反馈。