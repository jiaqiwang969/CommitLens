from __future__ import annotations

from pathlib import Path
from typing import Optional
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from .codex_runner import run_codex_exec, run_codex_exec_streaming


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
        f"5) 最终请确认 algorithm_flow.svg 与 algorithm_flow.pdf 均已生成。\n\n"
        f"提示：当前执行可能由于某些原因中断，请继续回顾一下已经完成的工作，然后继续完成上述任务。\n"
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

    if save_output:
        # Stream outputs to files; pre-create placeholders for UI discovery
        out_path = figs_dir / "codex_puml_output.txt"
        err_path = figs_dir / "codex_puml_error.txt"
        status_path = figs_dir / "codex_puml_status.txt"
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
            cwd=figs_dir,
            timeout_sec=timeout_sec,
            api_key=api_key,
            out_path=out_path,
            err_path=err_path,
            status_path=status_path,
        )

        # Post-check: ensure expected outputs exist; if missing, mark as failure and update status/err
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
                # Append missing info into error log and update status
                try:
                    with err_path.open("a", encoding="utf-8") as fh:
                        fh.write(f"\nmissing outputs: {', '.join(missing)}\n")
                except Exception:
                    pass
                try:
                    status_path.write_text(str(code), encoding="utf-8")
                except Exception:
                    pass
        except Exception:
            pass
        return code
    else:
        code, out, err = run_codex_exec(prompt, cwd=figs_dir, timeout_sec=timeout_sec, api_key=api_key)
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
    force: bool = False,
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

    # If forcing rerun: delete previous puml status+error (keep output) in figs dirs
    if force and (not dry_run):
        for d in targets:
            p = _find_algorithm_flow_puml(d)
            if not p:
                continue
            figs_dir = p.parent
            try:
                (figs_dir / "codex_puml_error.txt").unlink(missing_ok=True)  # Python 3.8? Use try/except
            except Exception:
                try:
                    f = figs_dir / "codex_puml_error.txt"
                    if f.exists():
                        f.unlink()
                except Exception:
                    pass
            try:
                (figs_dir / "codex_puml_status.txt").unlink(missing_ok=True)
            except Exception:
                try:
                    f = figs_dir / "codex_puml_status.txt"
                    if f.exists():
                        f.unlink()
                except Exception:
                    pass

    # Resume behavior: skip ones already successfully fixed
    skipped_ok: list[Path] = []
    to_run: list[Path] = []
    for d in targets:
        figs_dir = _find_algorithm_flow_puml(d)
        if figs_dir is None:
            to_run.append(d)
            continue
        figs_dir = figs_dir.parent
        status_file = figs_dir / "codex_puml_status.txt"
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

    targets = to_run

    total = len(targets)
    if total == 0:
        try:
            if skipped_ok:
                skipped_names = ", ".join(d.name for d in skipped_ok)
                print(f"[puml] 已跳过已成功的目录: {skipped_names}", flush=True)
            print("[puml] 无需处理，所有任务均已完成或无待处理项", flush=True)
        except Exception:
            pass
        return 0

    try:
        print(f"::progress::puml total {total}", flush=True)
        print(f"[puml] 链条总提交数={chain_total} 本次任务(含puml)={total}", flush=True)
        if total > 2:
            workers = min(max(1, int(max_parallel)), total)
            print(f"::progress::puml parallel {workers}", flush=True)
        if skipped_ok:
            skipped_names = ", ".join(d.name for d in skipped_ok)
            print(f"[puml] 已跳过已成功的目录: {skipped_names}", flush=True)
    except Exception:
        pass

    # Pre-create queued files for to-run targets so UI can see them immediately
    if save_output and (not dry_run):
        for d in targets:
            puml = _find_algorithm_flow_puml(d)
            if not puml:
                continue
            figs_dir = puml.parent
            try:
                out_path = figs_dir / "codex_puml_output.txt"
                err_path = figs_dir / "codex_puml_error.txt"
                status_path = figs_dir / "codex_puml_status.txt"
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
        # Failure summary for sequential path
        if worst != 0:
            pending: list[str] = []
            failed: list[str] = []
            for d in targets:
                p = _find_algorithm_flow_puml(d)
                figs_dir = p.parent if p else (d / "figs")
                try:
                    s_path = figs_dir / "codex_puml_status.txt"
                    s = s_path.read_text(encoding="utf-8").strip() if s_path.exists() else ""
                except Exception:
                    s = ""
                sl = s.lower()
                if (not s) or sl.startswith("queued") or sl.startswith("running"):
                    pending.append(d.name)
                else:
                    try:
                        ok = int(s) == 0
                    except Exception:
                        ok = s.upper() in ("OK", "SUCCESS")
                    if not ok:
                        failed.append(d.name)
            try:
                if pending:
                    print(f"[puml] 被打断，尚有待处理: {', '.join(pending)}", flush=True)
                if failed:
                    print(f"[puml] 失败目录: {', '.join(failed)}", flush=True)
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
    # Failure summary for parallel path
    if worst != 0:
        pending: list[str] = []
        failed: list[str] = []
        for d in targets:
            p = _find_algorithm_flow_puml(d)
            figs_dir = p.parent if p else (d / "figs")
            try:
                s_path = figs_dir / "codex_puml_status.txt"
                s = s_path.read_text(encoding="utf-8").strip() if s_path.exists() else ""
            except Exception:
                s = ""
            sl = s.lower()
            if (not s) or sl.startswith("queued") or sl.startswith("running"):
                pending.append(d.name)
            else:
                try:
                    ok = int(s) == 0
                except Exception:
                    ok = s.upper() in ("OK", "SUCCESS")
                if not ok:
                    failed.append(d.name)
        try:
            if pending:
                print(f"[puml] 被打断，尚有待处理: {', '.join(pending)}", flush=True)
            if failed:
                print(f"[puml] 失败目录: {', '.join(failed)}", flush=True)
        except Exception:
            pass
    return worst
