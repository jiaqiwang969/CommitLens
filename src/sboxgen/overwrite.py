from __future__ import annotations

from pathlib import Path
import shutil
from typing import Optional


def _find_commit_dir(root: Path, key: str) -> Optional[Path]:
    """Resolve a commit directory under root given a key.

    Key can be an exact directory name like '001-abcdefg', or a shorthand like
    '001-commit' (used by some report filenames). Fall back to matching the
    numeric prefix before the first dash.
    """
    exact = root / key
    if exact.exists() and exact.is_dir():
        return exact
    # Fallback: numeric prefix match
    prefix = key.split("-", 1)[0]
    for d in sorted(root.iterdir()):
        if d.is_dir() and d.name.startswith(f"{prefix}-"):
            return d
    return None


def overwrite_from_artifacts(
    artifacts_dir: Path,
    dest_root: Path,
    overwrite_reports: bool = True,
    overwrite_figs: bool = True,
    quiet: bool = False,
) -> int:
    """Overwrite reports and figs from artifacts into timeline sboxes.

    - Reports: copy artifacts/reports/<name>.tex -> dest_root/<commit>/reports/<name>.tex
      where <commit> resolves from <name> (numeric prefix fallback).
    - Figs: for each artifacts/figs/<commit>/, replace dest_root/<commit>/figs/<commit>/
      with a recursive copy of the source directory.
    """
    artifacts_dir = artifacts_dir.resolve()
    dest_root = dest_root.resolve()

    if not artifacts_dir.exists() or not artifacts_dir.is_dir():
        print(f"artifacts not found: {artifacts_dir}")
        return 2
    if not dest_root.exists() or not dest_root.is_dir():
        print(f"timeline root not found: {dest_root}")
        return 2

    # Reports
    if overwrite_reports:
        reports_dir = artifacts_dir / "reports"
        if reports_dir.exists() and reports_dir.is_dir():
            for f in sorted(reports_dir.glob("*.tex")):
                name = f.stem  # e.g., 001-abcdefg or 001-commit
                commit_dir = _find_commit_dir(dest_root, name)
                if commit_dir is None:
                    if not quiet:
                        print(f"[reports] skip (no dest commit): {name} -> {dest_root}")
                    continue
                dst_reports = commit_dir / "reports"
                dst_reports.mkdir(parents=True, exist_ok=True)
                dst = dst_reports / f.name
                try:
                    shutil.copy2(f, dst)
                    if not quiet:
                        print(f"[{commit_dir.name}] overwrote report -> {dst}")
                except Exception as e:
                    print(f"[{commit_dir.name}] failed to copy report {f.name}: {e}")

    # Figs
    if overwrite_figs:
        figs_root = artifacts_dir / "figs"
        if figs_root.exists() and figs_root.is_dir():
            for src_commit_dir in sorted([p for p in figs_root.iterdir() if p.is_dir()]):
                name = src_commit_dir.name  # commit name like 001-abcdefg
                commit_dir = _find_commit_dir(dest_root, name)
                if commit_dir is None:
                    if not quiet:
                        print(f"[figs] skip (no dest commit): {name} -> {dest_root}")
                    continue
                dst_commit_figs = commit_dir / "figs" / name
                # Replace the entire target commit figs subtree to avoid stale files
                try:
                    if dst_commit_figs.exists():
                        shutil.rmtree(dst_commit_figs)
                    dst_commit_figs.mkdir(parents=True, exist_ok=True)
                    copied = 0
                    for f in src_commit_dir.rglob("*"):
                        if not f.is_file():
                            continue
                        # Copy common graphic artifacts back; skip logs
                        ext = f.suffix.lower()
                        if ext not in (".pdf", ".svg", ".png", ".jpg", ".jpeg", ".puml"):
                            continue
                        rel = f.relative_to(src_commit_dir)
                        out_f = dst_commit_figs / rel
                        out_f.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.copy2(f, out_f)
                            copied += 1
                        except Exception:
                            pass
                    if not quiet:
                        print(f"[{commit_dir.name}] overwrote figs -> {dst_commit_figs} ({copied} files)")
                except Exception as e:
                    print(f"[{commit_dir.name}] failed to overwrite figs from {src_commit_dir}: {e}")

    return 0

