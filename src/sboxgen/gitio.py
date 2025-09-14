from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional

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
    """Prefer existing name between master/main if ambiguous; else return input."""
    if branch in ("master", "main"):
        env = default_env({"GIT_DIR": str(mirror_dir)})
        def _exists(br: str) -> bool:
            for ref in (f"refs/heads/{br}", f"refs/remotes/origin/{br}"):
                code, _, _ = run(["git", "rev-parse", "--verify", ref], check=False, env=env)
                if code == 0:
                    return True
            code, _, _ = run(["git", "rev-parse", "--verify", br], check=False, env=env)
            return code == 0
        has_master = _exists("master")
        has_main = _exists("main")
        if has_master and not has_main:
            return "master"
        if has_main and not has_master:
            return "main"
    return branch


def _resolve_branch_ref(mirror_dir: Path, branch: str) -> Optional[str]:
    """Return the best ref for a branch: refs/heads/<b> or refs/remotes/origin/<b>."""
    env = default_env({"GIT_DIR": str(mirror_dir)})
    for ref in (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"):
        code, _, _ = run(["git", "rev-parse", "--verify", ref], check=False, env=env)
        if code == 0:
            return ref
    return None


def list_commits(mirror_dir: Path, branch: str) -> Tuple[List[Commit], str]:
    # Always operate on the bare mirror via GIT_DIR; avoid -C which would pick parent repo
    env = default_env({"GIT_DIR": str(mirror_dir)})
    run(["git", "fetch", "--all", "--prune"], check=False, env=env)
    branch = resolve_branch(mirror_dir, branch)
    ref = _resolve_branch_ref(mirror_dir, branch) or branch
    _, out, _ = run(["git", "rev-list", "--first-parent", "--reverse", ref], env=env)
    revs = [r for r in out.splitlines() if r]
    commits: List[Commit] = []
    for sha in revs:
        _, title, _ = run(["git", "show", "-s", "--format=%s", sha], env=env)
        _, author, _ = run(["git", "show", "-s", "--format=%an <%ae>", sha], env=env)
        _, date, _ = run(["git", "show", "-s", "--format=%aI", sha], env=env)
        commits.append(Commit(sha=sha, short=sha[:7], title=title.strip(), author=author.strip(), datetime=date.strip()))
    return commits, branch


def count_commits_fast(mirror_dir: Path, branch: str) -> Tuple[int, str]:
    """Count commits along first-parent chain for a branch using an existing mirror.

    - Does NOT fetch/update remotes; purely local and very fast.
    - Resolves between master/main if the other exists locally.
    - Returns (count, resolved_branch). If branch not found, returns (0, input branch).
    """
    env = default_env({"GIT_DIR": str(mirror_dir)})
    # best-effort resolve master/main when ambiguous
    br = resolve_branch(mirror_dir, branch)
    ref = _resolve_branch_ref(mirror_dir, br) or br
    code, out, _ = run(["git", "rev-list", "--first-parent", "--count", ref], check=False, env=env)
    if code != 0:
        return 0, branch
    try:
        return int(out.strip() or "0"), br
    except Exception:
        return 0, br


def ensure_mirror_branch(repo: str, mirror_dir: Path, branch: str) -> Path:
    """Create or update a bare repo that only fetches the specified branch.

    - If mirror exists, only fetch the branch refs from origin (no tags; prune).
    - If not, init bare and add origin, then fetch only needed branch.
    - For master/main ambiguity, fetch both and let resolve_branch decide.
    """
    ensure_dir(mirror_dir.parent)
    env = default_env({"GIT_DIR": str(mirror_dir)})
    if (mirror_dir / "HEAD").exists():
        # ensure remote exists and set URL
        run(["git", "remote", "remove", "origin"], check=False, env=env)
        run(["git", "remote", "add", "origin", repo], env=env)
    else:
        # init bare repo and attach origin
        run(["git", "init", "--bare", str(mirror_dir)])
        env = default_env({"GIT_DIR": str(mirror_dir)})
        run(["git", "remote", "add", "origin", repo], env=env)

    # Fetch only specific branch refs (no tags); handle master/main ambiguity
    refspecs: List[str]
    if branch in ("master", "main"):
        refspecs = [
            "+refs/heads/master:refs/heads/master",
            "+refs/heads/main:refs/heads/main",
        ]
    else:
        refspecs = [f"+refs/heads/{branch}:refs/heads/{branch}"]
    run(["git", "fetch", "--prune", "--no-tags", "origin", *refspecs], env=env)
    return mirror_dir


def list_local_branches(mirror_dir: Path) -> List[str]:
    """List branch names in the mirror: heads and origin/* merged."""
    env = default_env({"GIT_DIR": str(mirror_dir)})
    names: set[str] = set()
    code, out, _ = run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"], check=False, env=env)
    if code == 0:
        for ln in out.splitlines():
            n = ln.strip()
            if n:
                names.add(n)
    code, out, _ = run(["git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"], check=False, env=env)
    if code == 0:
        for ln in out.splitlines():
            n = ln.strip()
            if not n:
                continue
            if n.startswith("origin/"):
                n = n[len("origin/"):]
            names.add(n)
    return sorted(names)


def update_all_branches(mirror_dir: Path, repo_url: Optional[str] = None) -> None:
    """Fetch all refs into refs/* (mirror-style), pruning deleted ones.

    Works even if repo wasn't created with --mirror.
    """
    ensure_dir(mirror_dir.parent)
    env = default_env({"GIT_DIR": str(mirror_dir)})
    if not (mirror_dir / "HEAD").exists():
        run(["git", "init", "--bare", str(mirror_dir)])
        env = default_env({"GIT_DIR": str(mirror_dir)})
    if repo_url:
        run(["git", "remote", "remove", "origin"], check=False, env=env)
        run(["git", "remote", "add", "origin", repo_url], env=env)
    # Mirror-style fetch to populate refs/* locally
    run(["git", "fetch", "--prune", "--no-tags", "origin", "+refs/*:refs/*"], check=False, env=env)
