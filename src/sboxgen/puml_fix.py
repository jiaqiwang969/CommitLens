from __future__ import annotations

from pathlib import Path
from typing import Optional
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from .codex_runner import run_codex_exec


def _find_algorithm_flow_puml(commit_dir: Path) -> Optional[Path]:
    figs = commit_dir / "figs"
    if not figs.exists() or not figs.is_dir():
        return None
    # Prefer direct child path figs/<anything>/algorithm_flow.puml, else any under figs
    candidates = list(figs.rglob("algorithm_flow.puml"))
    if candidates:
        # Choose the shortest path (closest to figs root)
        candidates.sort(key=lambda p: len(p.parts))
        return candidates[0]
    return None


def build_puml_fix_prompt(figs_dir: Path) -> str:
    d = str(figs_dir.resolve())

    # Overrides via env vars, support placeholder {dir}
    file_override = os.environ.get("SBOXGEN_CODEX_PUML_PROMPT_FILE")
    if file_override:
        fp = Path(file_override)
        if fp.exists():
            try:
                tmpl = fp.read_text(encoding="utf-8")
                return tmpl.replace("{dir}", d)
            except Exception:
                pass
    text_override = os.environ.get("SBOXGEN_CODEX_PUML_PROMPT")
    if text_override:
        try:
            return text_override.replace("{dir}", d)
        except Exception:
            pass

    return (
        f"请进入到‘{d}’，检查并编译 PlantUML：\n"
        f"1) 运行：plantuml -tsvg algorithm_flow.puml 生成 SVG；\n"
        f"2) 若出现如 ‘Error line N in file ...’ 的错误，请打开并修复 algorithm_flow.puml 中的问题（语法、引号、未闭合括号、缺少 @startuml/@enduml 等）；\n"
        f"3) 修复后再次编译确保无错误；\n"
        f"4) 将生成的 SVG 使用 rsvg-convert 转成 PDF：rsvg-convert -f pdf -o algorithm_flow.pdf algorithm_flow.svg；\n"
        f"   如本机无 rsvg-convert，可采用 macOS 的 sips 作为兜底：sips -s format pdf algorithm_flow.svg --out algorithm_flow.pdf；\n"
        f"5) 最终请确认 algorithm_flow.svg 与 algorithm_flow.pdf 均已生成。\n"
    )


def run_puml_one(commit_dir: Path, dry_run: bool = False, save_output: bool = True, timeout_sec: Optional[int] = None, api_key: Optional[str] = None) -> int:
    commit_dir = commit_dir.resolve()
    puml = _find_algorithm_flow_puml(commit_dir)
    if not puml:
        # Nothing to do
        return 0
    figs_dir = puml.parent
    prompt = build_puml_fix_prompt(figs_dir)
    if dry_run:
        safe = prompt.replace("\n", "\\n").replace('"', '\\"')
        print(f"DRY-RUN codex exec --skip-git-repo-check --sandbox workspace-write \"{safe}\"")
        return 0

    code, out, err = run_codex_exec(prompt, cwd=figs_dir, timeout_sec=timeout_sec, api_key=api_key)
    # Post-check: ensure expected outputs exist
    try:
        svg_ok = (figs_dir / "algorithm_flow.svg").exists()
        pdf_ok = (figs_dir / "algorithm_flow.pdf").exists()
        if code == 0 and not (svg_ok and pdf_ok):
            code = 1
            missing = []
            if not svg_ok:
                missing.append("algorithm_flow.svg")
            if not pdf_ok:
                missing.append("algorithm_flow.pdf")
            err = (err or "") + f"\nmissing outputs: {', '.join(missing)}"
    except Exception:
        pass
    if save_output:
        (figs_dir / "codex_puml_output.txt").write_text(out or "", encoding="utf-8")
        (figs_dir / "codex_puml_error.txt").write_text(err or "", encoding="utf-8")
        (figs_dir / "codex_puml_status.txt").write_text(str(code), encoding="utf-8")
    else:
        print(out or "")
        if err:
            print(err)
    return code


def run_puml_batch(
    root: Path,
    limit: int = 0,
    dry_run: bool = False,
    save_output: bool = True,
    timeout_sec: Optional[int] = None,
    api_key: Optional[str] = None,
    max_parallel: int = 100,
) -> int:
    root = root.resolve()
    commit_dirs = [d for d in sorted(root.iterdir()) if d.is_dir()]
    chain_total = len(commit_dirs)
    if limit:
        commit_dirs = commit_dirs[:limit]

    # Filter only those that actually contain algorithm_flow.puml
    targets: list[Path] = []
    for d in commit_dirs:
        if _find_algorithm_flow_puml(d):
            targets.append(d)

    total = len(targets)
    if total == 0:
        return 0

    try:
        print(f"::progress::puml total {total}", flush=True)
        print(f"::progress::puml max_parallel {int(max_parallel)}", flush=True)
        # GUI 参数读取：在 Codex 与参数页显示并发上限
        print(f"::param::puml max_parallel {int(max_parallel)}", flush=True)
        print(f"[puml] 链条总提交数={chain_total} 本次任务(含puml)={total}", flush=True)
        if total > 2:
            workers = min(max(1, int(max_parallel)), total)
            print(f"::progress::puml parallel {workers}", flush=True)
        try:
            print(f"[puml] 并发上限(max_parallel)={int(max_parallel)}", flush=True)
        except Exception:
            pass
    except Exception:
        pass

    # If small, run sequentially
    if total <= 2:
        worst = 0
        for d in targets:
            print(f"[puml] {d.name}")
            code = run_puml_one(d, dry_run=dry_run, save_output=save_output, timeout_sec=timeout_sec, api_key=api_key)
            worst = max(worst, 0 if code == 0 else 1)
            try:
                print("::progress::puml tick", flush=True)
            except Exception:
                pass
        return worst

    worst = 0
    for d in targets:
        print(f"[puml] {d.name}")

    workers = min(max(1, int(max_parallel)), total)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fut_map = {ex.submit(run_puml_one, d, dry_run, save_output, timeout_sec, api_key): d for d in targets}
        for fut in as_completed(fut_map):
            code = fut.result()
            worst = max(worst, 0 if code == 0 else 1)
            try:
                print("::progress::puml tick", flush=True)
            except Exception:
                pass
    return worst
