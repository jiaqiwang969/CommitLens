from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List

from .utils import ensure_dir


TEMPLATES_ROOT = Path('.cache/templates')


def list_templates(root: Path | None = None) -> List[str]:
    base = (root or TEMPLATES_ROOT).resolve()
    if not base.exists():
        return []
    names: List[str] = []
    for p in sorted(base.iterdir()):
        if p.is_dir():
            names.append(p.name)
    return names


def copy_template(name: str, dest: Path, root: Path | None = None, overwrite: bool = False) -> Path:
    base = (root or TEMPLATES_ROOT).resolve()
    src = base / name
    if not src.exists() or not src.is_dir():
        raise FileNotFoundError(f"template not found: {src}")
    ensure_dir(dest)
    # Copy content of template root into dest (merge)
    for item in src.rglob('*'):
        rel = item.relative_to(src)
        target = dest / rel
        if item.is_dir():
            ensure_dir(target)
        else:
            if target.exists() and not overwrite:
                # skip existing files
                continue
            ensure_dir(target.parent)
            shutil.copy2(item, target)
    return dest

