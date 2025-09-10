from __future__ import annotations

import datetime as _dt
import shutil
import subprocess
from pathlib import Path
import os
from typing import Optional, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


def _which(cmd: str) -> Optional[str]:
    p = shutil.which(cmd)
    return p


def build_prompt(commit_dir: Path) -> str:
    d = str(commit_dir.resolve())
    # Allow overrides via env vars for GUI or CLI users
    # - SBOXGEN_CODEX_PROMPT_FILE: path to a UTF-8 file with optional {dir}
    # - SBOXGEN_CODEX_PROMPT: prompt text with optional {dir}
    file_override = os.environ.get("SBOXGEN_CODEX_PROMPT_FILE")
    if file_override:
        fp = Path(file_override)
        if fp.exists():
            try:
                tmpl = fp.read_text(encoding="utf-8")
                return tmpl.replace("{dir}", d)
            except Exception:
                pass
    text_override = os.environ.get("SBOXGEN_CODEX_PROMPT")
    if text_override:
        try:
            return text_override.replace("{dir}", d)
        except Exception:
            pass

    # Default prompt
    return (
        f"请进入到如下目录，然后根据 README.md 的要求完成指定任务，并输出‘产出目标’：\n"
        f"目录：{d}\n\n"
        f"要求：\n"
        f"1) 切换到该目录后阅读 README.md；\n"
        f"2) 按 README 中的‘产出目标’完成对应操作（可创建/修改本目录下的 reports/figs 等文件）；\n"
        f"3) 完成后将本次产出在标准输出简要列出（例如生成的 fragment.tex、图表等）；\n"
        f"4) 遇到依赖缺失可做最小替代（如仅生成占位文件并标注 TODO）。\n\n"
        f"提示：当前执行可能由于某些原因中断，请继续回顾一下已经完成的工作，然后继续按照 README.md 的要求完成任务。\n"
    )


def run_codex_exec(prompt: str, cwd: Optional[Path] = None, timeout_sec: Optional[int] = None, api_key: Optional[str] = None) -> tuple[int, str, str]:
    exe = _which("codex")
    if not exe:
        return 127, "", "codex not found in PATH"
    cmd = [
        exe,
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        prompt,
    ]
    try:
        env = os.environ.copy()
        if api_key:
            env["CODEX_API_KEY"] = api_key
        p = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        out, err = p.communicate(timeout=timeout_sec)
        if isinstance(out, bytes):
            out = out.decode('utf-8', errors='replace')
        if isinstance(err, bytes):
            err = err.decode('utf-8', errors='replace')
        return p.returncode, out or "", err or ""
    except subprocess.TimeoutExpired as te:
        try:
            p.kill()
        except Exception:
            pass
        out = te.stdout or ""
        err = te.stderr or "timeout"
        if isinstance(out, bytes):
            out = out.decode('utf-8', errors='replace')
        if isinstance(err, bytes):
            err = err.decode('utf-8', errors='replace')
        return 124, out, err


def _has_error_markers_tail(out: str, tail_lines: int = 10) -> tuple[bool, list[str]]:
    """Heuristically detect failure by scanning ONLY the last N lines of stdout.

    This avoids false positives from earlier log content. Returns (has_error, markers).
    """
    try:
        lines = out.splitlines()
        tail = "\n".join(lines[-tail_lines:]) if lines else ""
    except Exception:
        tail = out
    hay = tail.lower()
    markers = [
        "error:",
        "stream error",
        "error sending request",
        "timed out",
        "timeout",
        "deadline exceeded",
        "connection reset",
        "broken pipe",
        "temporary failure in name resolution",
        "service unavailable",
        "bad gateway",
        "too many requests",
        "rate limit",
        "invalid api key",
        "unauthenticated",
        "certificate verify failed",
    ]
    hit = [m for m in markers if m in hay]
    return (len(hit) > 0, hit)


def run_codex_exec_streaming(
    prompt: str,
    cwd: Optional[Path] = None,
    timeout_sec: Optional[int] = None,
    api_key: Optional[str] = None,
    out_path: Optional[Path] = None,
    err_path: Optional[Path] = None,
    status_path: Optional[Path] = None,
) -> tuple[int, str, str]:
    """
    Run codex exec and stream stdout/stderr to files as they arrive.

    Returns (exit_code, full_stdout, full_stderr).
    """
    exe = _which("codex")
    if not exe:
        # Create files early so they exist even if codex is missing
        if out_path:
            out_path.write_text("", encoding="utf-8")
        if err_path:
            err_path.write_text("codex not found in PATH\n", encoding="utf-8")
        if status_path:
            status_path.write_text("127", encoding="utf-8")
        return 127, "", "codex not found in PATH"

    cmd = [
        exe,
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        prompt,
    ]

    env = os.environ.copy()
    if api_key:
        env["CODEX_API_KEY"] = api_key

    # Ensure the report files exist and status is visible immediately
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("", encoding="utf-8")
    if err_path:
        err_path.parent.mkdir(parents=True, exist_ok=True)
        err_path.write_text("", encoding="utf-8")
    if status_path:
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text("running", encoding="utf-8")

    p = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,  # line-buffered in text mode
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    stdout_acc: list[str] = []
    stderr_acc: list[str] = []

    # Open files for appending and stream writes
    out_fh = out_path.open("a", encoding="utf-8") if out_path else None
    err_fh = err_path.open("a", encoding="utf-8") if err_path else None

    def _copy_stream(src, dst_file, acc_list):
        try:
            if src is None:
                return
            for line in src:
                acc_list.append(line)
                if dst_file is not None:
                    dst_file.write(line)
                    dst_file.flush()
        except Exception:
            # Best-effort: ignore stream errors
            pass

    t_out = threading.Thread(target=_copy_stream, args=(p.stdout, out_fh, stdout_acc), daemon=True)
    t_err = threading.Thread(target=_copy_stream, args=(p.stderr, err_fh, stderr_acc), daemon=True)
    t_out.start()
    t_err.start()

    code: int
    try:
        code = p.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        try:
            p.kill()
        except Exception:
            pass
        code = 124
        if err_fh is not None:
            err_fh.write(f"\n[timeout after {timeout_sec}s]\n")
            err_fh.flush()

    # Ensure readers complete
    t_out.join(timeout=5)
    t_err.join(timeout=5)

    # Close files
    if out_fh is not None:
        out_fh.close()
    if err_fh is not None:
        err_fh.close()

    # Update final status
    if status_path:
        try:
            status_path.write_text(str(code), encoding="utf-8")
        except Exception:
            pass

    return code, "".join(stdout_acc), "".join(stderr_acc)


def run_one(commit_dir: Path, dry_run: bool = False, save_output: bool = True, timeout_sec: Optional[int] = None, api_key: Optional[str] = None) -> int:
    commit_dir = commit_dir.resolve()
    prompt = build_prompt(commit_dir)
    if dry_run:
        safe = prompt.replace("\n", "\\n").replace('"', '\\"')
        print(f"DRY-RUN codex exec --skip-git-repo-check --sandbox workspace-write \"{safe}\"")
        return 0
    if save_output:
        # Stream directly into report files so they update during execution
        out_path = commit_dir / "codex_output.txt"
        err_path = commit_dir / "codex_error.txt"
        status_path = commit_dir / "codex_status.txt"
        code, out, err = run_codex_exec_streaming(
            prompt,
            cwd=commit_dir,
            timeout_sec=timeout_sec,
            api_key=api_key,
            out_path=out_path,
            err_path=err_path,
            status_path=status_path,
        )
        # If exit code is 0 but we detect error markers in logs, override to failure
        has_err, hits = _has_error_markers_tail(out)
        if code == 0 and has_err:
            code = 1
            try:
                with err_path.open("a", encoding="utf-8") as fh:
                    fh.write("\n[post-check] detected error markers: " + ", ".join(hits) + "\n")
                status_path.write_text(str(code), encoding="utf-8")
            except Exception:
                pass
    else:
        # No file saving: run and print to terminal after completion
        code, out, err = run_codex_exec(prompt, cwd=commit_dir, timeout_sec=timeout_sec, api_key=api_key)
        if code == 0:
            has_err, _hits = _has_error_markers_tail(out)
            if has_err:
                code = 1
        print(out)
        if err:
            print(err)
    return code


def run_batch(
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
    all_dirs = [d for d in sorted(root.iterdir()) if d.is_dir()]

    # Helper to detect successful runs via codex_status.txt
    def _is_success(d: Path) -> bool:
        p = d / "codex_status.txt"
        if not p.exists():
            return False
        try:
            s = p.read_text(encoding="utf-8").strip()
        except Exception:
            return False
        if not s:
            return False
        sl = s.lower()
        if sl.startswith("running") or sl.startswith("queued"):
            # Stale/in-progress marker: treat as not successful
            return False
        try:
            ok = int(s) == 0
        except Exception:
            # Be tolerant of non-numeric success markers
            us = s.upper()
            ok = us in ("OK", "SUCCESS")
        if ok:
            # Additional safeguard: scan ONLY the last 10 lines of codex_output.txt
            try:
                out_path = d / "codex_output.txt"
                out_text = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
                has_err, _hits = _has_error_markers_tail(out_text, tail_lines=10)
                if has_err:
                    return False
            except Exception:
                pass
        return ok

    dirs = list(all_dirs)
    if limit:
        dirs = dirs[:limit]

    # If forcing rerun: delete previous status+error to disable skip
    if force and (not dry_run):
        for d in dirs:
            try:
                err_f = d / "codex_error.txt"
                st_f = d / "codex_status.txt"
                if err_f.exists():
                    err_f.unlink()
                if st_f.exists():
                    st_f.unlink()
            except Exception:
                pass

    # Resume behavior: skip directories with successful status
    skipped_ok: list[Path] = []
    to_run: list[Path] = []
    for d in dirs:
        if _is_success(d):
            skipped_ok.append(d)
        else:
            to_run.append(d)

    dirs = to_run

    total = len(dirs)
    chain_total = len(all_dirs)
    if total == 0:
        # Nothing to run; if some were skipped as OK, emit a friendly note
        try:
            if skipped_ok:
                skipped_names = ", ".join(d.name for d in skipped_ok)
                print(f"[codex] 已跳过已成功的目录: {skipped_names}", flush=True)
            print("[codex] 无需处理，所有任务均已完成或无待处理项", flush=True)
        except Exception:
            pass
        return 0

    # progress: total equals number of commit dirs to process
    # Emit progress and summary (actual parallel and task list)
    try:
        print(f"::progress::codex total {total}", flush=True)
        print(f"[codex] 链条总提交数={chain_total} 本次任务={total}", flush=True)
        if skipped_ok:
            skipped_names = ", ".join(d.name for d in skipped_ok)
            print(f"[codex] 已跳过已成功的目录: {skipped_names}", flush=True)
        actual_workers = 1
        if total > 2:
            actual_workers = min(max(1, int(max_parallel)), total)
            print(f"::progress::codex parallel {actual_workers}", flush=True)
        # Human-readable confirmation lines for GUI logs
        names = ", ".join(d.name for d in dirs)
        print(f"[codex] 本次实际并发={actual_workers} 总任务={total}", flush=True)
        print(f"[codex] 待处理: {names}", flush=True)
    except Exception:
        pass

    # Pre-create report files so UI/file watchers can discover them before execution starts
    if save_output and (not dry_run):
        for d in dirs:
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
                # best effort
                pass

    if total <= 2:
        worst = 0
        for d in dirs:
            print(f"[codex] {d.name}")
            code = run_one(d, dry_run=dry_run, save_output=save_output, timeout_sec=timeout_sec, api_key=api_key)
            worst = max(worst, 0 if code == 0 else 1)
            try:
                print("::progress::codex tick", flush=True)
            except Exception:
                pass
        return worst

    max_workers = min(max(1, int(max_parallel)), total)
    worst = 0
    for d in dirs:
        print(f"[codex] {d.name}")

    def _task(path: Path) -> int:
        try:
            print(f"[codex] start {path.name}", flush=True)
        except Exception:
            pass
        code = run_one(path, dry_run=dry_run, save_output=save_output, timeout_sec=timeout_sec, api_key=api_key)
        try:
            print(f"[codex] done {path.name} exit={code}", flush=True)
        except Exception:
            pass
        return code

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_map = {ex.submit(_task, d): d for d in dirs}
        for fut in as_completed(future_map):
            code = fut.result()
            worst = max(worst, 0 if code == 0 else 1)
            try:
                print("::progress::codex tick", flush=True)
            except Exception:
                pass
    return worst
