from __future__ import annotations

from pathlib import Path
from typing import Optional
import datetime as _dt

from .codex_runner import run_codex_exec, run_codex_exec_streaming, _which
import os


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
    prompt = build_latex_fix_prompt(artifacts_dir, tex_name=tex_name, runs=runs)

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
