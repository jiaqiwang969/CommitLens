# 提交考古说明（Timeline 风格）

本目录面向“某一次提交”的解读素材，采用 timeline 视角：聚焦当前提交（head）及其最多两个前置提交（head-1、head-2），以相邻提交对的 diff 作为主要证据。

上下文（来自 git）
- 提交：{sha}（{short}） — {title}
- 作者：{author}
- 日期：{datetime}
- 上一提交（可选）：{prev_short}

项目背景（Foxtrot 简介）
- Foxtrot 是一个面向 STEP（ISO 10303-21）文件、覆盖从标准解析到三角化再到渲染全链路、支持本地 GUI 与 WebAssembly 的快速查看器/演示项目，使用 Rust 语言实现。

目录与证据
- 子目录：
  - `head/`：当前提交快照（HEAD）
  - `head-1/`：上一个提交（HEAD~1），若存在
  - `head-2/`：上上个提交（HEAD~2），若存在
- 差异文件（相邻对）：
  - `HEAD.diff`：`head-1 → head` 的差异（若无 head-1，则为 `git show HEAD`）
  - `HEAD-1.diff`：`head-2 → head-1` 的差异（若无 head-2，则为 `git show HEAD~1`）
  - `HEAD-2.diff`：`head-3 → head-2` 的差异（若无 head-3，则为 `git show HEAD~2`）

写作顺序（建议）
1) 先读 `HEAD.diff`，用 3–5 句总结“改了什么/为什么/影响何在”（可引用具体 hunks）。
2) 若存在 `HEAD-1.diff`/`HEAD-2.diff`，补充两点“演进脉络”：从 `head-2 → head-1 → head` 的动机与取舍。
3) 提炼 2–3 个关键证据片段（文件+行区间），阐明对接口、数据结构、算法或边界条件的影响。
4) 如涉及结构或算法变化，使用 PlantUML 画 1–2 张小图-中文内容。

产出目标与命名规则（重要）
- Markdown：学习摘要 + 证据摘录（来自 `HEAD*.diff`）
- TeX：
  - 提交报告主文件（必须）：`reports/{seq_str}-{short}.tex`（与目录名一致，如 `{seq_str}-{short}.tex`）。
  - 图片位于figs/{seq_str}-{short}/下面，需要根据要求转成svg和pdf之后，才能引用。（重要，需要核对是否成功编译）

必答清单（用证据回答）
- 改了什么：列出 2–3 处关键改动（文件 + 行号段）。
- 为什么改：作者意图与权衡（性能/正确性/维护性）。
- 影响何在：对调用路径、构建、边界条件的影响与风险。
- 如何验证：编译/测试/样例/基准的最小验证方案。

TeX 片段模板示例
```tex
% 明确说明（非常重要），tex必须以\section开头，不能有其他内容，不能使用begin「document」
% (重要)tex书写规范：参考templates模版中的《LaTeX 编译常见问题与通用解决方案.md》
\section{提交考古：{seq_str}-{short}}

\subsection*{Commit 元信息}
\begin{itemize}
  \item 标题：{title}
  \item 作者：{author}
  \item 日期：{datetime}
\end{itemize}

% 可选：在此小节概述本次改动的主要文件与影响点（可从 HEAD.diff 的 diffstat 中手动摘录关键行）。
\subsection*{变更摘要（阅读提示）}
% 建议：从 HEAD.diff 的开头几行（包含 diffstat）手动摘取 1–3 行，帮助读者把握范围。

\subsection*{差异解读（证据）}
% 结合 HEAD.diff / HEAD-1.diff / HEAD-2.diff，分点说明改了什么、为何而改、影响何在

% 图示（必选）：若你绘制了 PlantUML 图并导出为 PDF/SVG，可在此引用
% \begin{figure}[h]
%   \centering
%   \includegraphics[width=0.4\linewidth]{{{seq_str}-{short}/architecture.pdf}}
%   \caption{架构变化要点}
% \end{figure}
```

学习补充（计算几何）
- 打开《计算几何教材.md》，按本次改动的关键词（如 orient2d/incircle/pseudo-angle/CDT 等）快速定位阅读。
- 在 TeX 的“基础知识补充”小节，提炼不超过 200 字的要点（给出阅读路径与结论，勿展开推导），并在解读中引用对应 `HEAD*.diff` 的证据。

图示生成指南
- 环境：本机 macOS 已安装 PlantUML/Graphviz，可直接导出。
- 路径：`figs/{seq_str}-{short}/architecture.puml` 与 `algorithm_flow.puml`。
- 参考模板：见本目录下 `template/basic` 与 `template/extended`。

提示：可以将本 README 作为“提示词”，连同本目录的 `HEAD*.diff` 提交给报告生成工具，自动生成初稿；再结合需求进行精炼与校对。


