from __future__ import annotations

from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .codex_runner import run_codex_exec_streaming, _has_error_markers_tail
from .puml_fix import _find_algorithm_flow_puml, build_puml_fix_prompt
from .latex_fix import build_latex_fix_shard_prompt
import os


def _find_main_commit_tex(commit_dir: Path) -> Optional[str]:
    """Find a main-*-commit.tex under commit_dir; fallback to single main.tex if exists.

    Returns the file name (not full path) or None.
    """
    cands = sorted(commit_dir.glob("main-*-commit.tex"))
    if cands:
        return cands[0].name
    mt = commit_dir / "main.tex"
    if mt.exists():
        return mt.name
    # Any other single main-*.tex
    cands2 = sorted(commit_dir.glob("main-*.tex"))
    if cands2:
        return cands2[0].name
    return None


def _build_combined_prompt(commit_dir: Path, tex_name: Optional[str], runs: int) -> str:
    """Combine PUML fix instructions and LaTeX compile instructions into one prompt.

    Allows override via env:
      - SBOXGEN_CODEX_TEX_FIX_PROMPT_FILE (UTF-8 file, supports {dir} {tex} {runs})
      - SBOXGEN_CODEX_TEX_FIX_PROMPT (text, supports {dir} {tex} {runs})
    """
    d = str(commit_dir.resolve())
    t = tex_name or "main.tex"
    # Overrides
    file_override = os.environ.get("SBOXGEN_CODEX_TEX_FIX_PROMPT_FILE")
    if file_override:
        fp = Path(file_override)
        if fp.exists():
            try:
                tmpl = fp.read_text(encoding="utf-8")
                return tmpl.replace("{dir}", d).replace("{tex}", t).replace("{runs}", str(runs))
            except Exception:
                pass
    text_override = os.environ.get("SBOXGEN_CODEX_TEX_FIX_PROMPT")
    if text_override:
        try:
            return text_override.replace("{dir}", d).replace("{tex}", t).replace("{runs}", str(runs))
        except Exception:
            pass
    # PUML part (only if we find a puml target under figs)
    puml_part = ""
    puml = _find_algorithm_flow_puml(commit_dir)
    if puml:
        puml_part = build_puml_fix_prompt(puml.parent)
    # LaTeX part (if tex is known)
    latex_part = ""
    if tex_name:
        latex_part = build_latex_fix_shard_prompt(commit_dir, tex_name=tex_name, runs=runs)
    else:
        latex_part = (
            f"请进入到{commit_dir.resolve()}，如果该目录存在 main-*-commit.tex 或 main.tex，"
            f"请使用 xelatex 编译并修复错误（循环多次直到无错误，可容许 warning）。"
        )

    # Merge both with a short coordinator hint
    joiner = (
        "\n\n注意：若图片 PDF/SVG 缺失或错误，请先完成上述 PUML 修复，再进行 LaTeX 编译；"
        "若编译仍失败，请交替检查并修复，直到 main*.pdf 成功生成。\n"
    )
    return (puml_part + ("\n\n" if puml_part else "") + latex_part + joiner)


def run_tex_fix_one(
    commit_dir: Path,
    runs: int = 3,
    dry_run: bool = False,
    save_output: bool = True,
    timeout_sec: Optional[int] = None,
    api_key: Optional[str] = None,
) -> int:
    commit_dir = commit_dir.resolve()
    tex_name = _find_main_commit_tex(commit_dir)
    prompt = _build_combined_prompt(commit_dir, tex_name, runs)
    if dry_run:
        safe = prompt.replace("\n", "\\n").replace('"', '\\"')
        print(f"DRY-RUN codex exec --skip-git-repo-check --sandbox workspace-write \"{safe}\"")
        return 0

    if save_output:
        out_path = commit_dir / "codex_output.txt"
        err_path = commit_dir / "codex_error.txt"
        status_path = commit_dir / "codex_status.txt"
        # Pre-create and set queued
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
            cwd=commit_dir,
            timeout_sec=timeout_sec,
            api_key=api_key,
            out_path=out_path,
            err_path=err_path,
            status_path=status_path,
        )
        # If exit code is 0 but output tail shows typical error markers, treat as failure
        if code == 0:
            has_err, _ = _has_error_markers_tail(out)
            if has_err:
                code = 1
                try:
                    with err_path.open("a", encoding="utf-8") as fh:
                        fh.write("\n[post-check] detected error markers in output tail\n")
                    status_path.write_text(str(code), encoding="utf-8")
                except Exception:
                    pass
        return code
    else:
        # Non-saving path not used by GUI; still execute and print to console
        from .codex_runner import run_codex_exec
        code, out, err = run_codex_exec(prompt, cwd=commit_dir, timeout_sec=timeout_sec, api_key=api_key)
        print(out or "")
        if err:
            print(err)
        return code


def run_tex_fix_batch(
    root: Path,
    limit: int = 0,
    runs: int = 3,
    dry_run: bool = False,
    save_output: bool = True,
    timeout_sec: Optional[int] = None,
    api_key: Optional[str] = None,
    max_parallel: int = 100,
    force: bool = False,
) -> int:
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        print(f"not found: {root}")
        return 2

    dirs = [d for d in sorted(root.iterdir()) if d.is_dir()]
    chain_total = len(dirs)
    if limit:
        dirs = dirs[:limit]

    # Force: remove previous status+error (keep outputs)
    if force and (not dry_run):
        for d in dirs:
            try:
                e = d / "codex_error.txt"
                s = d / "codex_status.txt"
                if e.exists():
                    e.unlink()
                if s.exists():
                    s.unlink()
            except Exception:
                pass

    # Resume: skip already successful ones
    to_run: list[Path] = []
    skipped_ok: list[Path] = []
    for d in dirs:
        status_file = d / "codex_status.txt"
        ok = False
        if status_file.exists():
            try:
                s = status_file.read_text(encoding="utf-8").strip()
                if s:
                    try:
                        ok = int(s) == 0
                    except Exception:
                        ok = s.upper() in ("OK", "SUCCESS")
            except Exception:
                ok = False
        if ok:
            skipped_ok.append(d)
        else:
            to_run.append(d)

    if not to_run:
        try:
            if skipped_ok:
                names = ", ".join(d.name for d in skipped_ok)
                print(f"[texfix] 已跳过已成功的目录: {names}", flush=True)
            print("[texfix] 无需处理，所有任务均已完成或无待处理项", flush=True)
        except Exception:
            pass
        return 0

    total = len(to_run)
    try:
        print(f"::progress::texfix total {total}", flush=True)
        print(f"[texfix] 链条总提交数={chain_total} 本次任务={total}", flush=True)
        if total > 2:
            workers = min(max(1, int(max_parallel)), total)
            print(f"::progress::texfix parallel {workers}", flush=True)
        if skipped_ok:
            names = ", ".join(d.name for d in skipped_ok)
            print(f"[texfix] 已跳过已成功的目录: {names}", flush=True)
    except Exception:
        pass

    # Pre-create queued markers for immediate UI discovery
    if save_output and (not dry_run):
        for d in to_run:
            try:
                out_path = d / "codex_output.txt"
                err_path = d / "codex_error.txt"
                status_path = d / "codex_status.txt"
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

    worst = 0
    if total <= 2:
        for d in to_run:
            print(f"[texfix] {d.name}")
            code = run_tex_fix_one(d, runs=runs, dry_run=dry_run, save_output=save_output, timeout_sec=timeout_sec, api_key=api_key)
            worst = max(worst, 0 if code == 0 else 1)
            try:
                print(f"::progress::texfix tick {d.name} exit={code}", flush=True)
            except Exception:
                pass
        return worst

    workers = min(max(1, int(max_parallel)), total)
    for d in to_run:
        print(f"[texfix] {d.name}")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fut_map = {ex.submit(run_tex_fix_one, d, runs, dry_run, save_output, timeout_sec, api_key): d for d in to_run}
        for fut in as_completed(fut_map):
            d = fut_map[fut]
            code = fut.result()
            worst = max(worst, 0 if code == 0 else 1)
            try:
                print(f"::progress::texfix tick {d.name} exit={code}", flush=True)
            except Exception:
                pass
    return worst
