from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from .utils import run, ensure_dir, default_env


@dataclass
class Commit:
    sha: str
    short: str
    title: str
    author: str
    datetime: str


def ensure_mirror(repo: str, mirror_dir: Path) -> Path:
    """Create or update a local bare mirror."""
    ensure_dir(mirror_dir.parent)
    if (mirror_dir / "HEAD").exists():
        # Use GIT_DIR to target the bare repo, avoiding parent worktree detection
        env = default_env({"GIT_DIR": str(mirror_dir)})
        run(["git", "remote", "update", "--prune"], env=env)  # best-effort
    else:
        run(["git", "clone", "--mirror", repo, str(mirror_dir)])
    return mirror_dir


def resolve_branch(mirror_dir: Path, branch: str) -> str:
    if branch in ("master", "main"):
        env = default_env({"GIT_DIR": str(mirror_dir)})
        code_m, out_m, _ = run(["git", "rev-parse", "--verify", "master"], check=False, env=env)
        code_n, out_n, _ = run(["git", "rev-parse", "--verify", "main"], check=False, env=env)
        if code_m != 0 and code_n == 0:
            return "main"
        if code_m == 0 and code_n != 0:
            return "master"
    return branch


def list_commits(mirror_dir: Path, branch: str) -> Tuple[List[Commit], str]:
    # Always operate on the bare mirror via GIT_DIR; avoid -C which would pick parent repo
    env = default_env({"GIT_DIR": str(mirror_dir)})
    run(["git", "fetch", "--all", "--prune"], check=False, env=env)
    branch = resolve_branch(mirror_dir, branch)
    _, out, _ = run(["git", "rev-list", "--first-parent", "--reverse", branch], env=env)
    revs = [r for r in out.splitlines() if r]
    commits: List[Commit] = []
    for sha in revs:
        _, title, _ = run(["git", "show", "-s", "--format=%s", sha], env=env)
        _, author, _ = run(["git", "show", "-s", "--format=%an <%ae>", sha], env=env)
        _, date, _ = run(["git", "show", "-s", "--format=%aI", sha], env=env)
        commits.append(Commit(sha=sha, short=sha[:7], title=title.strip(), author=author.strip(), datetime=date.strip()))
    return commits, branch
