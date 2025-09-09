from __future__ import annotations

from pathlib import Path
from typing import Optional
import datetime as _dt

from .codex_runner import run_codex_exec, _which
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
        f"然后再用sips -s format pdf \"$s\" --out \"${{s%.svg}}.pdf\" 生成正确的pdf，以修复图片的问题。"
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

    if dry_run:
        safe = prompt.replace("\n", "\\n").replace('"', '\\"')
        print(f"DRY-RUN codex exec --skip-git-repo-check --sandbox workspace-write \"{safe}\"")
        return 0

    # Fallback check: xelatex existence is not mandatory because Codex may install or handle errors,
    # but we still surface a note if it's missing, without failing the run preemptively.
    # We always run codex in artifacts_dir CWD.
    code, out, err = run_codex_exec(prompt, cwd=artifacts_dir, timeout_sec=timeout_sec, api_key=api_key)
    if save_output:
        ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        (artifacts_dir / f"codex_fix_output.txt").write_text(out or "", encoding="utf-8")
        (artifacts_dir / f"codex_fix_error.txt").write_text(err or "", encoding="utf-8")
        (artifacts_dir / f"codex_fix_status.txt").write_text(str(code), encoding="utf-8")
    else:
        print(out or "")
        if err:
            print(err)
    return code
