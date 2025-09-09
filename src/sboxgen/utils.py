from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Iterable, Optional, Tuple


class RunError(RuntimeError):
    def __init__(self, code: int, cmd: list[str] | str, out: str, err: str):
        self.code = code
        self.cmd = cmd
        self.out = out
        self.err = err
        super().__init__(f"command failed ({code}): {cmd}\n{err or out}")


def run(cmd: Iterable[str] | str, cwd: Optional[Path] = None, check: bool = True, env: Optional[dict] = None) -> Tuple[int, str, str]:
    shell = isinstance(cmd, str)
    proc = subprocess.Popen(
        cmd if shell else list(cmd),
        cwd=str(cwd) if cwd else None,
        text=True,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    out, err = proc.communicate()
    if check and proc.returncode != 0:
        raise RunError(proc.returncode, cmd if shell else list(cmd), out, err)
    return proc.returncode, out or "", err or ""


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def abspath(p: str | Path) -> str:
    return str(Path(p).resolve())


def short_sha(sha: str, n: int = 7) -> str:
    return sha[:n]


def default_env(base: Optional[dict] = None) -> dict:
    env = dict(os.environ)
    if base:
        env.update(base)
    env.setdefault("LC_ALL", "C")
    # Normalize git output for determinism
    return env
