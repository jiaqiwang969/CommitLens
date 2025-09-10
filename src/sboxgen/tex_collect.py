from __future__ import annotations

from pathlib import Path
import shutil
from typing import Optional

from .utils import ensure_dir


def _choose_report_tex(reports_dir: Path, commit_name: str) -> Optional[str]:
    """Select the best report .tex file name within a reports directory.

    Preference order:
    1) reports/<commit_name>.tex
    2) reports/<NNN>-commit.tex (derived from commit_name's numeric prefix)
    3) any non-fragment *.tex (first in sorted order)
    4) reports/fragment.tex (renamed to <commit_name>.tex when referenced)
    Returns the file name to reference under reports/ (not a full path).
    """
    if not reports_dir.exists() or not reports_dir.is_dir():
        return None

    cand = reports_dir / f"{commit_name}.tex"
    if cand.exists():
        return cand.name

    # Prefer <NNN>-commit.tex among others
    nnn = commit_name.split("-", 1)[0]
    alt_commit = reports_dir / f"{nnn}-commit.tex"
    if alt_commit.exists():
        return alt_commit.name

    # Any other non-fragment .tex
    others = sorted([p for p in reports_dir.glob("*.tex") if p.name != "fragment.tex"])  # includes alt_commit if exists
    if others:
        return others[0].name

    frag = reports_dir / "fragment.tex"
    if frag.exists():
        # Fallback to fragment.tex in-place for per-commit main
        return "fragment.tex"

    return None


def _write_main_commit_tex(dest_commit_dir: Path, commit_name: str, report_name: Optional[str]) -> Path:
    """Create main-<commit>-commit.tex inside dest_commit_dir that inputs the chosen report.

    If report_name is None, writes a minimal placeholder main telling the user to add a report.
    """
    stem = commit_name
    out = dest_commit_dir / f"main-{stem}-commit.tex"
    if report_name:
        input_line = f"\\input{{reports/{report_name}}}"
    else:
        input_line = "% TODO: add a report .tex under reports/ and update this input"

    # Keep this LaTeX preamble aligned with the existing shards generator
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
        f"\\title{{CommitLens 单提交编译：{stem}}}",
        "\\author{}",
        "\\date{\\today}",
        "",
        "\\begin{document}",
        "\\maketitle",
        "\\tableofcontents",
        "",
        input_line,
        "",
        "\\end{document}",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def collect_timeline_to_tex(src_root: Path, dest_root: Path, overwrite: bool = False, quiet: bool = False) -> int:
    """Create .sboxes_timeline_tex from .sboxes_timeline with per-commit minimal contents.

    For each commit under src_root, create dest_root/<commit>/ that keeps only:
    - reports/ (all files and subdirectories)
    - figs/ (all files and subdirectories)
    And generate main-<commit>-commit.tex that inputs the chosen report .tex.
    """
    src_root = src_root.resolve()
    dest_root = dest_root.resolve()
    if not src_root.exists() or not src_root.is_dir():
        print(f"not found: {src_root}")
        return 2
    ensure_dir(dest_root)

    commit_dirs = [d for d in sorted(src_root.iterdir()) if d.is_dir()]
    for commit_dir in commit_dirs:
        name = commit_dir.name
        out_dir = dest_root / name
        if out_dir.exists() and overwrite:
            shutil.rmtree(out_dir)
        ensure_dir(out_dir)

        # Copy reports and figs recursively if present, with filters:
        # - skip any *.txt files
        # - under figs/, skip any path under a directory that ends with "-commit"
        for sub in ("reports", "figs"):
            src = commit_dir / sub
            dst = out_dir / sub
            if not (src.exists() and src.is_dir()):
                continue
            if dst.exists():
                shutil.rmtree(dst)
            # Recreate and copy filtered
            dst.mkdir(parents=True, exist_ok=True)
            copied = 0
            for f in src.rglob("*"):
                if not f.is_file():
                    continue
                if f.suffix.lower() == ".txt":
                    continue
                if sub == "figs":
                    # If any part of the relative path endswith('-commit'), skip
                    rel_parts = f.relative_to(src).parts
                    if any(p.endswith("-commit") for p in rel_parts[:-1]):
                        continue
                rel = f.relative_to(src)
                out_f = dst / rel
                out_f.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(f, out_f)
                    copied += 1
                except Exception:
                    pass
            if not quiet:
                print(f"[{name}] copied {sub}/ -> {dst} ({copied} files, no *.txt; figs/*-commit pruned)")

        # Determine report to include and write main-<commit>-commit.tex
        report_name = _choose_report_tex(out_dir / "reports", name)
        main_tex = _write_main_commit_tex(out_dir, name, report_name)
        if not quiet:
            print(f"[{name}] wrote {main_tex.name}")

    if not quiet:
        print(f"OK collected timeline tex -> {dest_root}")
    return 0
