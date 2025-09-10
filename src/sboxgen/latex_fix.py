from __future__ import annotations

from pathlib import Path
from typing import Optional
import datetime as _dt

from .codex_runner import run_codex_exec, run_codex_exec_streaming, _which
from .codex_runner import _has_error_markers_tail
import os
import shutil as _sh

# Directory under artifacts to host parallel shard mains and their logs
_SHARD_DIR_NAME = "并行测试"


def build_latex_fix_prompt(artifacts_dir: Path, tex_name: str = "main.tex", runs: int = 3) -> str:
    d = str(artifacts_dir.resolve())

    # Overrides via env vars, support placeholders {dir}, {tex}, {runs}
    file_override = os.environ.get("SBOXGEN_CODEX_LATEX_PROMPT_FILE")
    if file_override:
        fp = Path(file_override)
        if fp.exists():
            try:
                tmpl = fp.read_text(encoding="utf-8")
                return (
                    tmpl.replace("{dir}", d)
                        .replace("{tex}", tex_name)
                        .replace("{runs}", str(runs))
                )
            except Exception:
                pass
    text_override = os.environ.get("SBOXGEN_CODEX_LATEX_PROMPT")
    if text_override:
        try:
            return (
                text_override.replace("{dir}", d)
                            .replace("{tex}", tex_name)
                            .replace("{runs}", str(runs))
            )
        except Exception:
            pass

    return (
        f"请进入到{d}，然后执行xelatex {tex_name}命令，帮我修复输出tex编译错误，最终生成完整的pdf文档，"
        f"需反复执行{runs}次，确认最终没有bug，可容许有warning。"
        f"注意，可能会碰到图片引用内容错误，这是由于图片pdf生成错误导致。需要进入到图片所在的目录，找到原始puml文件，然后，重新利用plantuml -tsvg编译，并修复错误。"
        f"然后再用sips -s format pdf \"$s\" --out \"${{s%.svg}}.pdf\" 生成正确的pdf，以修复图片的问题。\n\n"
        f"提示：当前执行可能由于某些原因中断，请继续回顾一下已经完成的工作，然后继续完成上述任务。\n"
    )


def build_latex_fix_shard_prompt(artifacts_dir: Path, tex_name: str, runs: int = 3) -> str:
    d = str(artifacts_dir.resolve())
    # Overrides via env vars: SBOXGEN_CODEX_LATEX_SHARDS_PROMPT[_FILE]
    file_override = os.environ.get("SBOXGEN_CODEX_LATEX_SHARDS_PROMPT_FILE")
    if file_override:
        fp = Path(file_override)
        if fp.exists():
            try:
                tmpl = fp.read_text(encoding="utf-8")
                return (
                    tmpl.replace("{dir}", d)
                        .replace("{tex}", tex_name)
                        .replace("{runs}", str(runs))
                )
            except Exception:
                pass
    text_override = os.environ.get("SBOXGEN_CODEX_LATEX_SHARDS_PROMPT")
    if text_override:
        try:
            return (
                text_override.replace("{dir}", d)
                            .replace("{tex}", tex_name)
                            .replace("{runs}", str(runs))
            )
        except Exception:
            pass
    # Default shards prompt: focus on a single tex and loop until errors are gone (warnings allowed)
    return (
        f"请进入到{d}，然后执行 xelatex {tex_name}，帮我修复输出 tex 编译错误，"
        f"一直循环执行直到最终没有错误为止，可容许有 warning。"
    )


def run_latex_fix(
    artifacts_dir: Path,
    tex_name: str = "main.tex",
    runs: int = 3,
    dry_run: bool = False,
    save_output: bool = True,
    timeout_sec: Optional[int] = None,
    api_key: Optional[str] = None,
) -> int:
    artifacts_dir = artifacts_dir.resolve()
    prompt = build_latex_fix_shard_prompt(artifacts_dir, tex_name=tex_name, runs=runs)

    # Resume behavior: if previous fix succeeded, skip
    status_file = artifacts_dir / "codex_fix_status.txt"
    if status_file.exists():
        try:
            s = status_file.read_text(encoding="utf-8").strip()
            ok = False
            if s:
                try:
                    ok = int(s) == 0
                except Exception:
                    ok = s.upper() in ("OK", "SUCCESS")
            if ok and not dry_run:
                try:
                    print(f"[fixbug] skip already successful: {artifacts_dir}")
                except Exception:
                    pass
                return 0
        except Exception:
            pass

    if dry_run:
        safe = prompt.replace("\n", "\\n").replace('"', '\\"')
        print(f"DRY-RUN codex exec --skip-git-repo-check --sandbox workspace-write \"{safe}\"")
        return 0

    # Stream outputs to files and pre-create placeholders for UI discovery
    if save_output and (not dry_run):
        out_path = artifacts_dir / "codex_fix_output.txt"
        err_path = artifacts_dir / "codex_fix_error.txt"
        status_path = artifacts_dir / "codex_fix_status.txt"
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            err_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            if not out_path.exists():
                out_path.write_text("", encoding="utf-8")
            if not err_path.exists():
                err_path.write_text("", encoding="utf-8")
            if not status_path.exists():
                status_path.write_text("queued", encoding="utf-8")
        except Exception:
            pass

        code, out, err = run_codex_exec_streaming(
            prompt,
            cwd=artifacts_dir,
            timeout_sec=timeout_sec,
            api_key=api_key,
            out_path=out_path,
            err_path=err_path,
            status_path=status_path,
        )
        return code
    else:
        # Non-saving path: run and print after completion
        code, out, err = run_codex_exec(prompt, cwd=artifacts_dir, timeout_sec=timeout_sec, api_key=api_key)
        print(out or "")
        if err:
            print(err)
        return code


def _write_single_main_tex(artifacts_dir: Path, report_name: str) -> Path:
    """Create artifacts_dir/并行测试/main-<stem>.tex and copy needed assets locally.

    - Writes main-<stem>.tex with local paths: \input{reports/<report>} and \graphicspath{{figs/}}
    - Copies artifacts_dir/reports/<report> -> 并行测试/reports/<report>
    - Copies artifacts_dir/figs/<stem>/**/*.{pdf,svg} -> 并行测试/figs/<stem>/**
    """
    stem = report_name.rsplit(".", 1)[0]
    shard_dir = artifacts_dir / _SHARD_DIR_NAME
    shard_dir.mkdir(parents=True, exist_ok=True)
    dst = shard_dir / f"main-{stem}.tex"
    body = [
        "% !TEX program = xelatex",
        "\\documentclass[12pt]{ctexart}",
        "\\usepackage{xeCJK}",
        "% Set Chinese fonts to avoid warnings - use available system fonts",
        "\\setCJKmainfont{Hiragino Sans GB}",
        "\\usepackage[margin=1in]{geometry}",
        "\\usepackage{hyperref}",
        "\\usepackage{graphicx}",
        "\\graphicspath{{figs/}}",
        "% Enforce uniform image width for all included graphics",
        "\\makeatletter",
        "\\let\\Oldincludegraphics\\includegraphics",
        "\\renewcommand{\\includegraphics}[2][]{\\Oldincludegraphics[width=0.4\\linewidth]{#2}}",
        "\\makeatother",
        "\\usepackage{amsmath,amssymb}",
        "\\DeclareMathOperator*{\\argmin}{arg\\,min}",
        "\\DeclareMathOperator*{\\argmax}{arg\\,max}",
        "\\usepackage{enumitem}",
        "\\usepackage{tikz}",
        "\\usepackage{float}",
        "\\usepackage{listings}",
        "\\usepackage{xcolor}",
        "\\usepackage{fvextra}",
        "",
        "% Define Rust language for listings",
        "\\lstdefinelanguage{Rust}{",
        "  keywords={",
        "    as, break, const, continue, crate, else, enum, extern, false, fn,",
        "    for, if, impl, in, let, loop, match, mod, move, mut, pub, ref,",
        "    return, self, Self, static, struct, super, trait, true, type,",
        "    unsafe, use, where, while, async, await, dyn",
        "  },",
        "  keywordstyle=\\color{blue}\\bfseries,",
        "  ndkeywords={",
        "    bool, u8, u16, u32, u64, u128, i8, i16, i32, i64, i128, f32, f64,",
        "    char, str, String, Vec, Option, Some, None, Result, Ok, Err",
        "  },",
        "  ndkeywordstyle=\\color{purple}\\bfseries,",
        "  identifierstyle=\\color{black},",
        "  sensitive=false,",
        "  comment=[l]{//},",
        "  morecomment=[s]{/*}{*/},",
        "  commentstyle=\\color{gray}\\ttfamily,",
        "  stringstyle=\\color{red}\\ttfamily,",
        "  morestring=[b]',",
        "  morestring=[b]\"\"",
        "}",
        "",
        "% Default listings settings",
        "\\lstset{",
        "  basicstyle=\\ttfamily\\footnotesize,",
        "  breaklines=true,",
        "  breakatwhitespace=true,",
        "  postbreak=\\mbox{\\textcolor{red}{$\\hookrightarrow$}\\space},",
        "  frame=single,",
        "  showstringspaces=false,",
        "  tabsize=2,",
        "  columns=flexible",
        "}",
        "\\setlist{nosep}",
        "",
        "% Configuration for better handling of long text",
        "\\sloppy",
        "\\emergencystretch=1em",
        "",
        f"\\title{{CommitLens 单条编译：{stem}}}",
        "\\author{}",
        "\\date{\\today}",
        "",
        "\\begin{document}",
        "\\maketitle",
        "\\tableofcontents",
        "",
        f"\\input{{reports/{report_name}}}",
        "\\end{document}",
    ]
    dst.write_text("\n".join(body), encoding="utf-8")

    # Copy report locally
    try:
        (shard_dir / "reports").mkdir(parents=True, exist_ok=True)
        src_report = artifacts_dir / "reports" / report_name
        if src_report.exists():
            _sh.copy2(src_report, shard_dir / "reports" / report_name)
    except Exception:
        pass

    # Copy figures for this commit locally
    try:
        local_figs_commit = shard_dir / "figs" / stem
        local_figs_commit.mkdir(parents=True, exist_ok=True)
        src_figs_commit = artifacts_dir / "figs" / stem
        if src_figs_commit.exists() and src_figs_commit.is_dir():
            for f in src_figs_commit.rglob("*"):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in (".pdf", ".svg"):
                    continue
                rel = f.relative_to(src_figs_commit)
                dstf = local_figs_commit / rel
                dstf.parent.mkdir(parents=True, exist_ok=True)
                try:
                    _sh.copy2(f, dstf)
                except Exception:
                    pass
    except Exception:
        pass
    return dst


def run_latex_fix_shard(
    artifacts_dir: Path,
    tex_name: str,
    runs: int = 3,
    dry_run: bool = False,
    save_output: bool = True,
    timeout_sec: Optional[int] = None,
    api_key: Optional[str] = None,
    force: bool = False,
) -> int:
    """Run codex fix for a single shard main-<commit>.tex with its own output files."""
    artifacts_dir = artifacts_dir.resolve()
    shard_dir = artifacts_dir / _SHARD_DIR_NAME
    shard_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_latex_fix_shard_prompt(shard_dir, tex_name=tex_name, runs=runs)
    stem = Path(tex_name).stem
    if dry_run:
        safe = prompt.replace("\n", "\\n").replace('"', '\\"')
        print(f"DRY-RUN codex exec --skip-git-repo-check --sandbox workspace-write \"{safe}\"")
        return 0

    out_path = shard_dir / f"codex_fix_output_{stem}.txt"

    if save_output:
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if not out_path.exists():
                out_path.write_text("", encoding="utf-8")
        except Exception:
            pass

        code, out, err = run_codex_exec_streaming(
            prompt,
            cwd=shard_dir,
            timeout_sec=timeout_sec,
            api_key=api_key,
            out_path=out_path,
            err_path=None,
            status_path=None,
        )

        if code == 0:
            has_err, hits = _has_error_markers_tail(out)
            if has_err:
                code = 1
        return code
    else:
        code, out, err = run_codex_exec(prompt, cwd=shard_dir, timeout_sec=timeout_sec, api_key=api_key)
        print(out or "")
        if err:
            print(err)
        return code


def run_latex_fix_shards_batch(
    artifacts_dir: Path,
    runs: int = 3,
    dry_run: bool = False,
    save_output: bool = True,
    timeout_sec: Optional[int] = None,
    api_key: Optional[str] = None,
    max_parallel: int = 100,
    force: bool = False,
) -> int:
    """Generate per-commit main-*.tex for each collected report and run Codex fix in parallel."""
    artifacts_dir = artifacts_dir.resolve()
    reports_dir = artifacts_dir / "reports"
    if not reports_dir.exists() or not reports_dir.is_dir():
        print(f"reports not found under {artifacts_dir}")
        return 2
    reports = sorted([p for p in reports_dir.glob("*.tex") if p.name != "main.tex"])
    if not reports:
        return 0

    mains: list[Path] = []
    for r in reports:
        mains.append(_write_single_main_tex(artifacts_dir, r.name))

    tasks: list[Path] = []
    skipped_ok: list[Path] = []
    shard_dir = artifacts_dir / _SHARD_DIR_NAME
    for m in mains:
        stem = m.stem
        out_path = shard_dir / f"codex_fix_output_{stem}.txt"
        ok = False
        try:
            if out_path.exists():
                out_text = out_path.read_text(encoding="utf-8")
                has_err, _ = _has_error_markers_tail(out_text or "")
                ok = (not has_err)
        except Exception:
            ok = False
        if ok and not force:
            skipped_ok.append(m)
        else:
            tasks.append(m)

    total = len(tasks)
    try:
        print(f"::progress::fixshards total {total}", flush=True)
        if skipped_ok:
            print(f"[fixshards] 已跳过已成功的: {', '.join(p.name for p in skipped_ok)}", flush=True)
    except Exception:
        pass
    if total == 0:
        return 0

    if save_output and (not dry_run):
        for m in tasks:
            stem = m.stem
            try:
                shard_dir.mkdir(parents=True, exist_ok=True)
                (shard_dir / f"codex_fix_output_{stem}.txt").write_text("", encoding="utf-8")
            except Exception:
                pass

    def _one(mp: Path) -> int:
        return run_latex_fix_shard(
            artifacts_dir=artifacts_dir,
            tex_name=mp.name,
            runs=runs,
            dry_run=dry_run,
            save_output=save_output,
            timeout_sec=timeout_sec,
            api_key=api_key,
            force=force,
        )

    worst = 0
    if total <= 2:
        for mp in tasks:
            code = _one(mp)
            worst = max(worst, 0 if code == 0 else 1)
            try:
                print("::progress::fixshards tick", flush=True)
            except Exception:
                pass
        return worst

    from concurrent.futures import ThreadPoolExecutor, as_completed
    workers = min(max(1, int(max_parallel)), total)
    try:
        print(f"::progress::fixshards parallel {workers}", flush=True)
    except Exception:
        pass
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fut_map = {ex.submit(_one, mp): mp for mp in tasks}
        for fut in as_completed(fut_map):
            code = fut.result()
            worst = max(worst, 0 if code == 0 else 1)
            try:
                print("::progress::fixshards tick", flush=True)
            except Exception:
                pass
    return worst
