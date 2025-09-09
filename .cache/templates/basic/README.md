Template: basic（按提交时间线）

目的
- 面向“某一次提交”的解读素材，采用 timeline 视角：聚焦当前提交（head）及其最多两个前置提交（head-1、head-2），以相邻提交对的 diff 作为主要证据。

目录与证据（本目录期望配套的文件）
- 子目录：`head/`、`head-1/`、`head-2/`（各自为该提交的快照，若存在）
- 差异文件（相邻对）：`HEAD.diff`、`HEAD-1.diff`、`HEAD-2.diff`
- 图示：`figs/<NNN>-<{curr.short}>/architecture.puml`、`figs/<NNN>-<{curr.short}>/algorithm_flow.puml`
- TeX 片段：`reports/fragment.tex`（可被主文档包含；或复制/命名为 `reports/<NNN>-<{curr.short}>.tex`）

必答清单（用证据回答）
- 改了什么：列出 2–3 处关键改动（文件 + 行号段）。
- 为什么改：作者意图与权衡（性能/正确性/维护性）。
- 影响何在：对调用路径、构建、边界条件的影响与风险。
- 如何验证：编译/测试/样例/基准的最小验证方案。

使用流程（建议）
1) 先读 `HEAD.diff`，用 3–5 句总结“改了什么/为什么/影响何在”（可引用具体 hunks）。
2) 若存在 `HEAD-1.diff`/`HEAD-2.diff`，补充两点“演进脉络”：从 `head-2 → head-1 → head` 的动机与取舍。
3) 在 “证据摘录” 小节填入 2–3 个关键片段（文件+行区间），指出接口/数据结构/算法/边界条件的影响。
4) 如涉及结构或算法变化，编辑 `figs/<NNN>-<{curr.short}>/*.puml` 画 1–2 张图示。
5) 在 “基础知识补充” 小节，打开《计算几何教材.md》，按关键词（如 orient2d/incircle/pseudo-angle/CDT）快速定位阅读，摘录不超过 200 字要点与结论。

图示（必选）与导出
- 必须产出两张图：
  - 架构图（architecture）：展示 before/after 的模块边界、依赖关系、数据路径，使用 <<added>>/<<removed>>/<<changed>> 标注关键变化；建议体现 STEP 解析 → 三角化 → 渲染 的链路与受影响模块。
  - 算法流程图（algorithm_flow）：展示入口、关键分支与循环、边界条件处理（如退化/数值鲁棒性）、终止条件与复杂度影响；必要时标注与 orient2d/incircle 等几何谓词的调用点。

图示导出（两种方式）
- 直接用 PlantUML/Graphviz：
  - 生成 SVG：`plantuml -tsvg -o . figs/<NNN>-<{curr.short}>/*.puml`
  - 转 PDF（其一）：`for s in figs/<NNN>-<{curr.short}>/*.svg; do rsvg-convert -f pdf -o "${s%.svg}.pdf" "$s"; done`
  - 转 PDF（macOS）：`for s in figs/<NNN>-<{curr.short}>/*.svg; do sips -s format pdf "$s" --out "${s%.svg}.pdf"; done`
- 或使用脚本：`bash scripts/gen_figs.sh <NNN>-<{curr.short}>`

TeX 片段
- 按模板编辑 `reports/fragment.tex`，从 `HEAD.diff` 的开头几行（包含 diffstat）手动摘取 1–3 行，填入“变更摘要（阅读提示）”。
- 在“差异解读（证据）”内按“改了什么/为什么改/影响何在/如何验证”作答并引用 `HEAD*.diff` 的证据。
- 在“图示与说明”内插入两张图（architecture.pdf / algorithm_flow.pdf），并用 3–5 句分别解释图示要点、影响范围与对应的 diff 证据。
 - 统一比例：插图按 `width=0.4\linewidth` 引用（模板已内置）。

最小验证建议（示例）
- 构建：`cargo build --release`（若本仓包含 Rust 项并可编译）；或在 `head/` 快照内构建。
- 测试：`cargo test --workspace`；或按项目自带脚本运行样例。
