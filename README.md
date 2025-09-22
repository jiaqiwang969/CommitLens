CommitLens · 从 Git 提交一键生成高质量变更报告（支持交互式提交图）

快速预览
- 示例 PDF → Example.pdf
- GUI 截图：
  - 主界面：界面.png
  - 设置：界面-设置.png

为什么用 CommitLens
- 一键把“提交历史”转成“可读、可交付”的报告（Markdown/TeX → PDF）。
- 交互式“commit info”页签：点击节点即可查看该提交的摘要、变更文件与 Diff。
- 既可图形化使用，也可纯命令行，默认配置开箱即用。

核心特性
- Timeline 生成：按提交序列输出 head/head-1/head-2 与相邻 diff，配套 README 模板。
- 交互式提交图（commit info）：左侧分支/提交关系图，右侧提交详情 + 文件树 + Diff/File 视图切换。
- 一键流水线：mirror → gen → verify →（可选）Codex 批量 → 收集/修复 → PDF → 回写。
- Codex Output 查看：实时解析 codex_output.txt，支持高亮与跳转。
- 模板管理：风格=模板，内置默认模板，支持导入/保存。
- 纯 CLI：适合 CI 与脚本化生产。

快速开始（2 分钟）
- GUI
  - 安装 Python 3.9+ 与 git，克隆本仓库。
  - 运行：python tools/sboxgen_gui.py
  - 在“基本设置”填入仓库/分支/提交数，点击“一键执行全部”。到“commit info”页签点击“交互渲染”。
- CLI（最少 3 步）
  - 镜像：commitlens mirror --repo <URL|PATH> --dest .cache/mirrors/repo.git
  - 生成：commitlens gen --mirror .cache/mirrors/repo.git --branch main --out .sboxes --limit 10
  - 校验：commitlens verify --root .sboxes

交互式提交图（commit info）
- 点击“交互渲染”绘制提交关系；点击节点即可查看右侧详情。
- 未显示？确认默认仓库路径 .workspace/rust-project 存在（可在“任务执行”页修改），或指定 git-graph 路径：
  - 环境变量：SBOXGEN_GIT_GRAPH=/path/to/git-graph

先决条件
- 必需：Python 3.9+、git
- 可选：PlantUML/Graphviz（图示）、librsvg 或 macOS sips（SVG 转 PDF/PNG）、Rust/cargo（构建本地 git-graph）

更多
- 进阶用法与更新记录见 docs/ 目录。
