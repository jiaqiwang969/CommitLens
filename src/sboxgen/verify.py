from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Tuple


def _ok_dir(p: Path) -> bool:
    return p.exists() and p.is_dir()


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def verify_sbox(sbox: Path, strict: bool = False) -> Tuple[bool, str]:
    name = sbox.name
    if not _ok_dir(sbox):
        return False, f"missing dir: {sbox}"
    ok = True
    msgs = []
    # accept styles:
    # - legacy: a_prev/b_curr/z_final + evidence.diff + meta.json
    # - head: a_prev/b_curr + HEAD.diff (+/- HEAD-1.diff)
    # - timeline: head[/head-1[/head-2]] + HEAD.diff + optional HEAD-1.diff/HEAD-2.diff
    legacy = (sbox / "evidence.diff").exists() and (sbox / "meta.json").exists()
    head_style = (sbox / "HEAD.diff").exists() or (sbox / "HEAD-1.diff").exists() or (sbox / "HEAD-2.diff").exists()
    if legacy:
        for sub in ("a_prev", "b_curr", "z_final"):
            d = sbox / sub
            if not _ok_dir(d):
                ok = False
                msgs.append(f"missing {sub}/")
    elif head_style:
        # Either head-style or timeline-style
        # Accept either (a_prev/b_curr) or (head[/head-1[/head-2]])
        has_ab = _ok_dir(sbox / "a_prev") and _ok_dir(sbox / "b_curr")
        has_heads = _ok_dir(sbox / "head")
        if not (has_ab or has_heads):
            ok = False
            msgs.append("missing worktrees: expect a_prev/b_curr or head")
        if not (sbox / "HEAD.diff").exists():
            ok = False
            msgs.append("missing HEAD.diff")
    else:
        ok = False
        msgs.append("missing evidence: no recognized style diffs found")
    # If legacy present, lightly validate meta
    if legacy:
        meta_path = sbox / "meta.json"
        meta = _read_json(meta_path)
        if not isinstance(meta, dict):
            ok = False
            msgs.append("meta.json invalid JSON")
        else:
            for k in ("seq", "curr", "prev", "final"):
                if k not in meta:
                    ok = False
                    msgs.append(f"meta.json missing {k}")
    # READY is optional now
    return ok, "; ".join(msgs) if msgs else "OK"
