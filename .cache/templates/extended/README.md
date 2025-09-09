Template: extended（结构化时间线 + 辅助脚本）

定位
- 针对“单次提交”的解读，采用 timeline 视角：关注 `head` 及其最多两个前置提交（`head-1`、`head-2`），以相邻提交对的 diff 为主要证据。

包含内容
- `figs/plantuml-theme.puml`：共享 PlantUML 样式。
- `figs/{architecture,algorithm_flow}.puml`：示例图，可按需要复制到 `figs/<NNN>-<{curr.short}>/` 下编辑。
- `reports/fragment.tex`：结构化的 TeX 片段模板，含“必答清单”。
- `scripts/gen_figs.sh`：图示导出脚本（SVG → PDF）。

目录与证据（建议）
- 子目录：`head/`、`head-1/`、`head-2/`（各对应提交快照）
- 差异：`HEAD.diff`、`HEAD-1.diff`、`HEAD-2.diff`（相邻对）
- 图示：`figs/<NNN>-<{curr.short}>/architecture.puml`、`figs/<NNN>-<{curr.short}>/algorithm_flow.puml`
- TeX：`reports/fragment.tex`（纳入主文档；或复制/命名为 `reports/<NNN>-<{curr.short}>.tex`）

写作顺序（建议）
1) 先读 `HEAD.diff`，用 3–5 句总结“改了什么/为什么/影响何在”（引用具体 hunks 更佳）。
2) 若存在 `HEAD-1.diff`/`HEAD-2.diff`，补充“演进脉络”：从 `head-2 → head-1 → head` 的动机与取舍。
3) 在 TeX 的“证据摘录”小节中填 2–3 个关键证据（文件+行区间），说明对接口/数据结构/算法或边界条件的影响。
4) 如涉及结构/算法变化，编辑 `figs/<NNN>-<{curr.short}>/*.puml` 绘制 1–2 张图示并导出。
5) 打开《计算几何教材.md》按本次改动关键词（orient2d/incircle/pseudo-angle/CDT 等）快速定位，写“基础知识补充”（≤200 字）。

图示（必选）与生成指南
- 必须产出两张图：
  - 架构图（architecture）：展示 before/after 的模块边界、依赖关系与数据路径；用 <<added>>/<<removed>>/<<changed>> 标注关键变化；建议体现 STEP 解析 → 三角化 → 渲染 的链路与受影响模块。
  - 算法流程图（algorithm_flow）：展示入口、关键分支与循环、边界条件处理（退化/数值鲁棒性）、终止条件与复杂度影响；标注 orient2d/incircle 等几何谓词的调用点（若相关）。
- 环境：本机 macOS 已安装 PlantUML/Graphviz，可直接导出。
- 路径：`figs/<NNN>-<{curr.short}>/architecture.puml` 与 `algorithm_flow.puml`。
- 导出方式 A（脚本）：`bash scripts/gen_figs.sh <NNN>-<{curr.short}>`
- 导出方式 B（手动）：
  1) 先生成 SVG：`plantuml -tsvg -o . figs/<NNN>-<{curr.short}>/*.puml`
  2) 再将 SVG 转为 PDF：
     - librsvg：`for s in figs/<NNN>-<{curr.short}>/*.svg; do rsvg-convert -f pdf -o "${s%.svg}.pdf" "$s"; done`
     - macOS：`for s in figs/<NNN>-<{curr.short}>/*.svg; do sips -s format pdf "$s" --out "${s%.svg}.pdf"; done`
- 引用：导出 PDF 后，在 TeX 片段中通过 `\includegraphics{figs/<NNN>-<{curr.short}>/architecture.pdf}` 与 `algorithm_flow.pdf` 引用。
 - 引用比例：统一 `width=0.4\linewidth`（模板已设置）。

必答清单（用证据回答）
- 改了什么：列出 2–3 处关键改动（文件 + 行号段）。
- 为什么改：作者意图与权衡（性能/正确性/维护性）。
- 影响何在：对调用路径、构建、边界条件的影响与风险。
- 如何验证：编译/测试/样例/基准的最小验证方案。

验证建议（示例）
- 构建：在 `head/` 快照内执行 `cargo build --release`（若为 Rust 项）。
- 测试：`cargo test --workspace`；如有集成示例，按项目脚本运行。

提示
- 可将本 README 作为“提示词”，连同本目录的 `HEAD*.diff` 提交给报告生成工具，自动生成初稿；再结合需求进行精炼与校对。
