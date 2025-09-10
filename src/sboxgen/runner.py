from __future__ import annotations

import sys
import shutil
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .templates import copy_template, TEMPLATES_ROOT
from .utils import ensure_dir, run


def _exec_script_if_exists(commit_dir: Path, rel: str, quiet: bool = False) -> int:
    script = commit_dir / rel
    if not script.exists():
        return 0
    code, out, err = run(["bash", str(script)], cwd=commit_dir, check=False)
    if not quiet:
        print(f"[{commit_dir.name}] {rel}: exit={code}")
        if out.strip():
            print(out.strip())
        if err.strip():
            print(err.strip())
    return code


def _copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    ensure_dir(dst.parent)
    shutil.copy2(src, dst)
    return True


def _write_main_tex(collect_root: Path, only_files: list[str] | None = None, quiet: bool = False) -> None:
    """Generate a main.tex under collect_root that aggregates collected reports.

    Only includes reports that have been collected (present under collect_root/reports).
    The generated document mirrors the reference structure and sets graphicspath to figs/.
    """
    reports_dir = collect_root / "reports"
    if not reports_dir.exists():
        return
    if only_files is not None:
        items = sorted(only_files)
    else:
        items = sorted([p.name for p in reports_dir.glob("*.tex")])
    if not items:
        return

    inputs = "\n".join(["\\input{reports/" + name + "}" for name in items])
    lines = [
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
        "\\title{Foxtrot 提交演进报告（CommitLens 汇总）}",
        "\\author{}",
        "\\date{\\today}",
        "",
        "\\begin{document}",
        "\\maketitle",
        "\\tableofcontents",
        "",
        "% 自动生成区段开始（由 sboxgen 维护）",
        "% BEGIN-AUTOGEN-REPORTS",
        inputs,
        "% END-AUTOGEN-REPORTS",
        "",
        "\\end{document}",
    ]
    content = "\n".join(lines)
    out = collect_root / "main.tex"
    out.write_text(content, encoding="utf-8")
    if not quiet:
        print(f"collected main.tex -> {out}")


def run_over_commits(
    root: Path,
    template_name: Optional[str] = None,
    apply_template: bool = False,
    overwrite_template: bool = False,
    exec_scripts: bool = True,
    collect_reports: bool = True,
    collect_figs: bool = False,
    collect_root: Optional[Path] = None,
    quiet: bool = False,
) -> None:
    """Traverse commit directories to apply template, execute scripts, and collect artifacts.

    - If apply_template: copy template into each commit dir (skip existing unless overwrite_template)
    - If exec_scripts: run known scripts (scripts/gen_figs.sh) with commit dir as CWD
    - If collect_reports: copy reports/fragment.tex to collect_root/reports/<commit>.tex
    - If collect_figs: copy figs/*.pdf to collect_root/figs/<commit>/
    """
    root = root.resolve()
    # Guard: root must exist and be a directory
    if not root.exists() or not root.is_dir():
        print(f"not found: {root}", file=sys.stderr)
        return
    if collect_root is not None:
        collect_root = collect_root.resolve()
        ensure_dir(collect_root)
        if collect_reports:
            ensure_dir(collect_root / "reports")
        if collect_figs:
            ensure_dir(collect_root / "figs")

    commit_dirs = sorted([p for p in root.iterdir() if p.is_dir()])

    collected_report_files: list[str] = []

    def _process(commit_dir: Path) -> None:
        name = commit_dir.name
        if apply_template and template_name:
            copy_template(template_name, commit_dir, TEMPLATES_ROOT, overwrite=overwrite_template)
            if not quiet:
                print(f"[{name}] template applied: {template_name}")

        if exec_scripts:
            _exec_script_if_exists(commit_dir, "scripts/gen_figs.sh", quiet=quiet)

        if collect_root is None:
            return

        # Collect commit report: prefer commit-specific report "reports/<NNN>-<short>.tex".
        # Do not collect template fragment.tex anymore.
        if collect_reports:
            # Priority:
            # 1) reports/<NNN>-<short>.tex
            # 2) any non-fragment .tex (prefer <NNN>-commit.tex if present)
            # 3) reports/fragment.tex (rename to <NNN>-<short>.tex in artifacts)
            reports_dir = commit_dir / "reports"
            cand = reports_dir / f"{name}.tex"
            alt_commit = reports_dir / f"{name.split('-', 1)[0]}-commit.tex"
            frag = reports_dir / "fragment.tex"

            chosen_src = None
            chosen_dst_name = None
            suffix = ""
            if cand.exists():
                chosen_src = cand
                chosen_dst_name = cand.name
            else:
                # gather other non-fragment tex files
                others = sorted([p for p in reports_dir.glob("*.tex") if p.name != "fragment.tex" and p.name != cand.name])
                # prefer <NNN>-commit.tex among others
                if alt_commit.exists():
                    chosen_src = alt_commit
                    chosen_dst_name = alt_commit.name
                    suffix = " (non-fragment fallback)"
                elif others:
                    chosen_src = others[0]
                    chosen_dst_name = chosen_src.name
                    suffix = " (non-fragment fallback)"
                elif frag.exists():
                    chosen_src = frag
                    chosen_dst_name = f"{name}.tex"
                    suffix = " (fragment fallback)"

            if chosen_src is not None:
                dst = collect_root / "reports" / chosen_dst_name
                if _copy_if_exists(chosen_src, dst) and not quiet:
                    print(f"[{name}] collected report{suffix} -> {dst}")
                collected_report_files.append(chosen_dst_name)

        # Collect figures (pdf)
        if collect_figs:
            figs_dir = commit_dir / "figs"
            if figs_dir.exists():
                out_dir = collect_root / "figs" / name
                ensure_dir(out_dir)
                # Copy artifacts recursively (pdf/svg/puml/txt), preserving relative subdirectories
                copied = 0
                for f in figs_dir.rglob("*"):
                    if not f.is_file():
                        continue
                    ext = f.suffix.lower()
                    if ext not in (".pdf", ".svg", ".puml", ".txt"):
                        continue
                    rel = f.relative_to(figs_dir)
                    # Flatten a leading commit-name directory (e.g., <commit>/<files> -> <files>)
                    parts = rel.parts
                    if len(parts) > 0 and parts[0] == name:
                        rel = Path(*parts[1:])
                    dst = out_dir / rel
                    ensure_dir(dst.parent)
                    if _copy_if_exists(f, dst):
                        copied += 1
                if not quiet:
                    print(f"[{name}] collected figs -> {out_dir} ({copied} files: pdf/svg/puml/txt; flattened)")
                # Remove redundant nested commit folder if present (e.g., <out_dir>/<commit>/...)
                nested = out_dir / name
                try:
                    if nested.exists() and nested.is_dir():
                        shutil.rmtree(nested)
                        if not quiet:
                            print(f"[{name}] pruned redundant nested dir: {nested}")
                except Exception:
                    pass

    total = len(commit_dirs)
    if total <= 2:
        for d in commit_dirs:
            _process(d)
        return

    max_workers = min(100, total)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_process, d) for d in commit_dirs]
        for _ in as_completed(futures):
            pass

    # Write aggregator main.tex if collecting into a root
    if collect_root is not None and (collect_reports or collect_figs):
        _write_main_tex(collect_root, only_files=(collected_report_files if collect_reports else None), quiet=quiet)
