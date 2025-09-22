# Git Graph 集成到 Python GUI 的实施方案

## 概述
将 git-graph (Rust 实现) 集成到 Python GUI 中有多种方案，每种都有其优缺点。

## 方案对比

### 方案1：SVG + Canvas 混合渲染
**文件**: `git_graph_integration.py`

**优点**:
- 视觉效果最佳，保留 git-graph 的完美布局
- 支持复杂的分支结构渲染
- 可以利用 git-graph 的所有视觉特性

**缺点**:
- 需要 SVG 到 PNG 转换工具
- 坐标映射较复杂
- 性能开销较大

**适用场景**:
- 需要高质量视觉效果
- 静态展示为主，交互较少
- 有足够的系统资源

### 方案2：数据桥接方案
**文件**: `git_graph_bridge.py`

**优点**:
- 灵活性高，可自定义渲染
- 纯 Python 实现，易于调试
- 可以与现有 Tkinter 代码无缝集成

**缺点**:
- 需要重新实现布局算法
- 可能无法完全复现 git-graph 的效果

**适用场景**:
- 需要深度定制
- 现有代码库较大，需要渐进式迁移
- 需要特殊的交互功能

### 方案3：Rust FFI 集成
**文件**: `git_graph_ffi_integration.py` + `git_graph_ffi.rs`

**优点**:
- 性能最优
- 直接使用 git-graph 的核心算法
- 数据结构化，易于扩展

**缺点**:
- 需要编译 Rust 代码为动态库
- 部署较复杂
- 需要处理跨平台兼容性

**适用场景**:
- 性能要求高
- 处理大型仓库
- 需要实时更新

## 实施步骤

### 快速开始（方案2 - 推荐）

1. **安装依赖**:
```bash
pip install pillow
```

2. **集成到现有 GUI**:
```python
from git_graph_bridge import GitGraphDataBridge, TkinterGraphRenderer

# 在你的 GUI 类中
def setup_graph_view(self):
    # 创建数据桥接器
    self.graph_bridge = GitGraphDataBridge()

    # 创建渲染器
    self.graph_renderer = TkinterGraphRenderer(self.canvas)

    # 渲染图形
    self.refresh_graph()

def refresh_graph(self):
    # 获取数据
    data = self.graph_bridge.get_graph_data(self.repo_path, limit=50)

    # 渲染
    self.graph_renderer.render(data)
```

### 高级集成（方案3 - FFI）

1. **编译 Rust 库**:

首先，修改 `src/git-graph/Cargo.toml` 添加:
```toml
[lib]
name = "git_graph"
crate-type = ["cdylib", "rlib"]

[dependencies]
serde_json = "1.0"
```

2. **添加 FFI 代码**:
将 `git_graph_ffi.rs` 的内容添加到 `src/git-graph/src/ffi.rs`

3. **编译**:
```bash
cd src/git-graph
cargo build --release
```

4. **Python 集成**:
```python
from git_graph_ffi_integration import OptimizedGraphRenderer

# 初始化
renderer = OptimizedGraphRenderer(canvas)
renderer.initialize_ffi()

# 渲染
renderer.render_repository(repo_path, limit=100)
```

## 性能优化建议

1. **缓存机制**:
```python
class CachedGraphRenderer:
    def __init__(self):
        self._cache = {}

    def get_graph_data(self, repo_path, limit):
        cache_key = f"{repo_path}:{limit}"
        if cache_key not in self._cache:
            self._cache[cache_key] = self._generate_data(repo_path, limit)
        return self._cache[cache_key]
```

2. **增量更新**:
- 只更新变化的部分
- 使用差分算法检测变化

3. **异步渲染**:
```python
import threading

def render_async(self, repo_path, limit):
    def _render():
        data = self.get_graph_data(repo_path, limit)
        self.root.after(0, lambda: self.render(data))

    thread = threading.Thread(target=_render, daemon=True)
    thread.start()
```

## 交互功能增强

1. **提交详情浮窗**:
```python
def show_commit_details(self, commit_hash):
    # 创建浮窗
    popup = tk.Toplevel(self.root)
    popup.title(f"Commit {commit_hash[:7]}")

    # 显示详细信息
    details = self.get_commit_details(commit_hash)
    text = tk.Text(popup, wrap=tk.WORD)
    text.insert("1.0", details)
    text.pack()
```

2. **分支过滤**:
```python
def filter_by_branch(self, branch_name):
    # 过滤特定分支的提交
    filtered_data = self.filter_graph_data(self.current_data, branch_name)
    self.renderer.render(filtered_data)
```

3. **搜索功能**:
```python
def search_commits(self, keyword):
    # 搜索提交信息
    results = []
    for node in self.current_data["nodes"]:
        if keyword.lower() in node["subject"].lower():
            results.append(node)

    # 高亮搜索结果
    self.highlight_nodes(results)
```

## 故障排除

### 常见问题

1. **git-graph 未找到**:
   - 设置环境变量: `export GIT_GRAPH_BIN=/path/to/git-graph`
   - 或在代码中指定路径

2. **SVG 转换失败**:
   - macOS: 自带 sips 工具
   - Linux: 安装 `rsvg-convert` 或 `inkscape`
   - Windows: 安装 `ImageMagick`

3. **FFI 加载失败**:
   - 确保编译为正确的架构 (x86_64, arm64)
   - 检查动态库路径
   - 使用 `ldd` (Linux) 或 `otool -L` (macOS) 检查依赖

## 最佳实践

1. **从简单开始**: 先使用方案2（数据桥接）快速集成
2. **渐进式改进**: 根据需求逐步优化性能和功能
3. **模块化设计**: 将渲染逻辑与业务逻辑分离
4. **错误处理**: 始终提供降级方案

## 示例项目结构

```
your_project/
├── tools/
│   ├── sboxgen_gui.py          # 主 GUI
│   ├── git_graph_bridge.py     # 数据桥接模块
│   └── git_graph_renderer.py   # 渲染模块
├── src/
│   └── git-graph/              # git-graph 源码
│       ├── src/
│       │   └── ffi.rs          # FFI 接口
│       └── target/
│           └── release/
│               └── libgit_graph.dylib
└── tests/
    └── test_graph_render.py    # 测试代码
```

## 结论

根据项目需求选择合适的方案：
- **快速原型**: 使用方案2
- **生产环境**: 使用方案3 (FFI)
- **视觉优先**: 使用方案1 (SVG)

建议从方案2开始，逐步迁移到方案3以获得最佳性能。