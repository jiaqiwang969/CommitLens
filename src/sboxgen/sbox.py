from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .gitio import Commit
from .utils import ensure_dir, run, default_env
from .templates import TEMPLATES_ROOT
import shutil as _sh


def _write_text(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")


def _write_readme_prompt(
    dst: Path,
    curr: Commit,
    prev: Optional[Commit],
) -> None:
    title = curr.title or "<subject>"
    prev_sha = prev.sha if prev else None
    seq_str = dst.name.split('-', 1)[0] if '-' in dst.name else '<NNN>'
    # Allow overriding README template via env vars (text or file). Placeholders supported:
    # {seq} {seq_str} {short} {sha} {title} {author} {datetime} {prev_sha} {prev_short}
    # 1) explicit file override via env
    tmpl_file = os.environ.get("SBOXGEN_SBOX_README_TEMPLATE_FILE")
    if tmpl_file:
        fp = Path(tmpl_file)
        if fp.exists():
            try:
                tmpl = fp.read_text(encoding="utf-8")
                mapping = {
                    "seq": seq_str,
                    "seq_str": seq_str,
                    "short": curr.short,
                    "sha": curr.sha,
                    "title": title,
                    "author": curr.author,
                    "datetime": curr.datetime,
                    "prev_sha": prev_sha or "",
                    "prev_short": (prev_sha[:7] if prev_sha else ""),
                }
                for k, v in mapping.items():
                    tmpl = tmpl.replace("{" + k + "}", str(v))
                (dst / "README.md").write_text(tmpl, encoding="utf-8")
                return
            except Exception:
                pass
    # 2) explicit inline override via env
    text_override = os.environ.get("SBOXGEN_SBOX_README_TEMPLATE")
    if text_override:
        try:
            tmpl = text_override
            mapping = {
                "seq": seq_str,
                "seq_str": seq_str,
                "short": curr.short,
                "sha": curr.sha,
                "title": title,
                "author": curr.author,
                "datetime": curr.datetime,
                "prev_sha": prev_sha or "",
                "prev_short": (prev_sha[:7] if prev_sha else ""),
            }
            for k, v in mapping.items():
                tmpl = tmpl.replace("{" + k + "}", str(v))
            (dst / "README.md").write_text(tmpl, encoding="utf-8")
            return
        except Exception:
            pass
    # 3) implicit local file default
    try:
        local_fp = Path.cwd() / ".cache/sbox_readme_template.md"
        if local_fp.exists():
            tmpl = local_fp.read_text(encoding="utf-8")
            mapping = {
                "seq": seq_str,
                "seq_str": seq_str,
                "short": curr.short,
                "sha": curr.sha,
                "title": title,
                "author": curr.author,
                "datetime": curr.datetime,
                "prev_sha": prev_sha or "",
                "prev_short": (prev_sha[:7] if prev_sha else ""),
            }
            for k, v in mapping.items():
                tmpl = tmpl.replace("{" + k + "}", str(v))
            (dst / "README.md").write_text(tmpl, encoding="utf-8")
            return
    except Exception:
        pass

    body = f"""# 提交考古说明（Timeline 风格）

本目录面向“某一次提交”的解读素材，采用 timeline 视角：聚焦当前提交（head）及其最多两个前置提交（head-1、head-2），以相邻提交对的 diff 作为主要证据。

上下文（来自 git）
- 提交：{curr.sha}（{curr.short}） — {title}
- 作者：{curr.author}
- 日期：{curr.datetime}
- 上一提交（可选）：{prev_sha[:7] if prev_sha else '<none>'}

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
  - 提交报告主文件（必须）：`reports/{seq_str}-{curr.short}.tex`（与目录名一致，如 `{seq_str}-{curr.short}.tex`）。
  - 图片位于figs/{seq_str}-{curr.short}/下面，需要根据要求转成svg和pdf之后，才能引用。（重要，需要核对是否成功编译）

必答清单（用证据回答）
- 改了什么：列出 2–3 处关键改动（文件 + 行号段）。
- 为什么改：作者意图与权衡（性能/正确性/维护性）。
- 影响何在：对调用路径、构建、边界条件的影响与风险。
- 如何验证：编译/测试/样例/基准的最小验证方案。

TeX 片段模板示例
```tex
% 明确说明（非常重要），tex必须以\section开头，不能有其他内容，不能使用begin「document」
% (重要)tex书写规范：参考templates模版中的《LaTeX 编译常见问题与通用解决方案.md》
\section{{提交考古：{seq_str}-{curr.short}}}

\subsection*{{Commit 元信息}}
\begin{{itemize}}
  \item 标题：{title}
  \item 作者：{curr.author}
  \item 日期：{curr.datetime}
\end{{itemize}}

% 可选：在此小节概述本次改动的主要文件与影响点（可从 HEAD.diff 的 diffstat 中手动摘录关键行）。
\subsection*{{变更摘要（阅读提示）}}
% 建议：从 HEAD.diff 的开头几行（包含 diffstat）手动摘取 1–3 行，帮助读者把握范围。

\subsection*{{差异解读（证据）}}
% 结合 HEAD.diff / HEAD-1.diff / HEAD-2.diff，分点说明改了什么、为何而改、影响何在

% 图示（必选）：若你绘制了 PlantUML 图并导出为 PDF/SVG，可在此引用
% \begin{{figure}}[h]
%   \centering
%   \includegraphics[width=0.4\linewidth]{{{seq_str}-{curr.short}/architecture.pdf}}
%   \caption{{架构变化要点}}
% \end{{figure}}
```

学习补充（计算几何）
- 打开《计算几何教材.md》，按本次改动的关键词（如 orient2d/incircle/pseudo-angle/CDT 等）快速定位阅读。
- 在 TeX 的“基础知识补充”小节，提炼不超过 200 字的要点（给出阅读路径与结论，勿展开推导），并在解读中引用对应 `HEAD*.diff` 的证据。

图示生成指南
- 环境：本机 macOS 已安装 PlantUML/Graphviz，可直接导出。
- 路径：`figs/<NNN>-<{curr.short}>/architecture.puml` 与 `algorithm_flow.puml`。
- 导出：
  1) 先生成 SVG：`plantuml -tsvg -o . figs/<NNN>-<{curr.short}>/*.puml`
  2) 再将 SVG 转为 PDF：
     - 若有 librsvg：`for s in figs/<NNN>-<{curr.short}>/*.svg; do rsvg-convert -f pdf -o "${{s%.svg}}.pdf" "$s"; done`
     - 否则（macOS）：`for s in figs/<NNN>-<{curr.short}>/*.svg; do sips -s format pdf "$s" --out "${{s%.svg}}.pdf"; done`
- 引用：将导出的 PDF 放入上述目录后，按 TeX 模板引用。
- 参考模板：见本目录下 `template/basic` 与 `template/extended`。

提示：可以将本 README 作为“提示词”，连同本目录的 `HEAD*.diff` 提交给报告生成工具，自动生成初稿；再结合需求进行精炼与校对。
"""
    (dst / "README.md").write_text(body, encoding="utf-8")


def checkout_tree(mirror_dir: Path, worktree: Path, sha: str, index_file: Optional[Path] = None) -> None:
    ensure_dir(worktree)
    env = default_env({
        "GIT_DIR": str(mirror_dir),
        "GIT_WORK_TREE": str(worktree),
    })
    if index_file is None:
        index_file = worktree.parent / f".git-index-{worktree.name}"
    env["GIT_INDEX_FILE"] = str(index_file)
    run(["git", "checkout", "-f", sha], env=env)


def write_evidence(mirror_dir: Path, worktree: Path, prev_sha: Optional[str], curr_sha: str, out_path: Path) -> None:
    env = default_env({
        "GIT_DIR": str(mirror_dir),
        "GIT_WORK_TREE": str(worktree),
    })
    if prev_sha and prev_sha != curr_sha:
        code, out, err = run(["git", "diff", "--stat", "--patch", prev_sha, curr_sha], env=env)
    else:
        code, out, err = run(["git", "show", "--stat", "--patch", curr_sha], env=env)
    _write_text(out_path, out)


def generate_one_sbox_legacy(
    root: Path,
    src_mirror: Path,
    seq: int,
    tip_sha: str,
    prev: Optional[Commit],
    curr: Commit,
    branch: str,
) -> Path:
    name = f"{seq:03d}-{curr.short}"
    sbox = root / name
    ensure_dir(sbox)

    # Worktrees using central mirror (no local mirror.git symlink)
    a_prev = sbox / "a_prev"
    b_curr = sbox / "b_curr"
    z_final = sbox / "z_final"
    for d in (a_prev, b_curr, z_final):
        ensure_dir(d)

    prev_sha = prev.sha if prev else curr.sha
    final_sha = tip_sha if curr.sha != tip_sha else curr.sha

    checkout_tree(src_mirror, a_prev, prev_sha)
    checkout_tree(src_mirror, b_curr, curr.sha)
    checkout_tree(src_mirror, z_final, final_sha)

    # Evidence
    write_evidence(src_mirror, b_curr, None if not prev else prev.sha, curr.sha, sbox / "evidence.diff")

    # Meta
    meta = {
        "seq": seq,
        "curr": curr.sha,
        "prev": prev_sha,
        "final": final_sha,
        "branch": branch,
        "title": curr.title,
        "author": curr.author,
        "datetime": curr.datetime,
    }
    _write_text(sbox / "meta.json", json.dumps(meta, ensure_ascii=False))
    (sbox / "READY").touch()
    return sbox


def generate_one_sbox_headstyle(
    root: Path,
    src_mirror: Path,
    seq: int,
    prev_prev: Optional[Commit],
    prev: Optional[Commit],
    curr: Commit,
) -> Path:
    """Generate minimal sbox for 'head' style: a_prev/b_curr + HEAD.diff + HEAD-1.diff + README.md.

    - No z_final, no meta.json, no mirror.git.
    - HEAD.diff   = diff (prev..curr) or show(curr) if no prev
    - HEAD-1.diff = diff (prev_prev..prev) or show(prev) if no prev_prev and prev exists
    """
    name = f"{seq:03d}-{curr.short}"
    sbox = root / name
    ensure_dir(sbox)

    a_prev = sbox / "a_prev"
    b_curr = sbox / "b_curr"
    ensure_dir(a_prev)
    ensure_dir(b_curr)

    prev_sha = prev.sha if prev else curr.sha
    checkout_tree(src_mirror, a_prev, prev_sha)
    checkout_tree(src_mirror, b_curr, curr.sha)

    # HEAD.diff
    write_evidence(src_mirror, b_curr, None if not prev else prev.sha, curr.sha, sbox / "HEAD.diff")
    # HEAD-1.diff
    if prev is None:
        # no previous commit; skip
        pass
    else:
        if prev_prev is None:
            # Use show(prev)
            env = default_env({
                "GIT_DIR": str(src_mirror),
                "GIT_WORK_TREE": str(b_curr),
            })
            _, out, _ = run(["git", "show", "--stat", "--patch", prev.sha], env=env)
            _write_text(sbox / "HEAD-1.diff", out)
        else:
            env = default_env({
                "GIT_DIR": str(src_mirror),
                "GIT_WORK_TREE": str(b_curr),
            })
            _, out, _ = run(["git", "diff", "--stat", "--patch", prev_prev.sha, prev.sha], env=env)
            _write_text(sbox / "HEAD-1.diff", out)

    # README prompt
    _write_readme_prompt(sbox, curr, prev)
    return sbox


def generate_one_sbox_timeline(
    root: Path,
    src_mirror: Path,
    seq: int,
    curr: Commit,
    prev1: Optional[Commit],
    prev2: Optional[Commit],
    prev3: Optional[Commit],
) -> Path:
    """Generate structured folder per commit:

    - Subdirs: head/ (curr), head-1/ (prev1 if exists), head-2/ (prev2 if exists)
    - Diff files:
      - HEAD.diff   = diff(prev1..curr) or show(curr) if no prev1
      - HEAD-1.diff = diff(prev2..prev1) or show(prev1) if no prev2 but prev1 exists
      - HEAD-2.diff = diff(prev3..prev2) or show(prev2) if no prev3 but prev2 exists
    - README.md: prompt-style instruction for report generation
    """
    name = f"{seq:03d}-{curr.short}"
    sbox = root / name
    ensure_dir(sbox)

    # Checkouts
    head = sbox / "head"
    ensure_dir(head)
    checkout_tree(src_mirror, head, curr.sha)
    if prev1 is not None:
        head1 = sbox / "head-1"
        ensure_dir(head1)
        checkout_tree(src_mirror, head1, prev1.sha)
    if prev2 is not None:
        head2 = sbox / "head-2"
        ensure_dir(head2)
        checkout_tree(src_mirror, head2, prev2.sha)

    # Diff helpers
    env = default_env({
        "GIT_DIR": str(src_mirror),
        "GIT_WORK_TREE": str(head),
    })

    # HEAD.diff
    if prev1 is None:
        _, out, _ = run(["git", "show", "--stat", "--patch", curr.sha], env=env)
        _write_text(sbox / "HEAD.diff", out)
    else:
        _, out, _ = run(["git", "diff", "--stat", "--patch", prev1.sha, curr.sha], env=env)
        _write_text(sbox / "HEAD.diff", out)

    # HEAD-1.diff
    if prev1 is not None:
        if prev2 is None:
            _, out, _ = run(["git", "show", "--stat", "--patch", prev1.sha], env=env)
            _write_text(sbox / "HEAD-1.diff", out)
        else:
            _, out, _ = run(["git", "diff", "--stat", "--patch", prev2.sha, prev1.sha], env=env)
            _write_text(sbox / "HEAD-1.diff", out)

    # HEAD-2.diff
    if prev2 is not None:
        if prev3 is None:
            _, out, _ = run(["git", "show", "--stat", "--patch", prev2.sha], env=env)
            _write_text(sbox / "HEAD-2.diff", out)
        else:
            _, out, _ = run(["git", "diff", "--stat", "--patch", prev3.sha, prev2.sha], env=env)
            _write_text(sbox / "HEAD-2.diff", out)

    # README prompt
    _write_readme_prompt(sbox, curr, prev1)

    # Copy textbook and templates (reference only)
    try:
        textbook = Path('.cache/计算几何教材.md')
        if textbook.exists():
            _sh.copy2(str(textbook), str(sbox / '计算几何教材.md'))
    except Exception:
        pass

    try:
        t_src = TEMPLATES_ROOT.resolve()
        t_dst = sbox / 'template'
        if t_src.exists():
            if t_dst.exists():
                # refresh to keep in sync
                _sh.rmtree(t_dst)
            _sh.copytree(str(t_src), str(t_dst))
    except Exception:
        pass
    # Remove any legacy shortstat files if present
    for fn in ("HEAD.shortstat", "HEAD-1.shortstat", "HEAD-2.shortstat"):
        p = sbox / fn
        try:
            p.unlink(missing_ok=True)  # py3.8+
        except TypeError:
            if p.exists():
                p.unlink()
    return sbox
