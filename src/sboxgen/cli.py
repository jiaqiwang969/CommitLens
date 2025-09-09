from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from .gitio import ensure_mirror, list_commits
from .sbox import (
    generate_one_sbox_legacy,
    generate_one_sbox_headstyle,
    generate_one_sbox_timeline,
)
from .verify import verify_sbox
from .utils import ensure_dir
from .templates import list_templates, copy_template, TEMPLATES_ROOT
from .runner import run_over_commits
from .codex_runner import run_one as codex_run_one, run_batch as codex_run_batch
from .puml_fix import run_puml_batch
from .latex_fix import run_latex_fix
import os


def cmd_mirror(args: argparse.Namespace) -> int:
    repo = args.repo
    dest = Path(args.dest).resolve() if args.dest else Path.cwd() / ".cache/mirrors/repo.git"
    ensure_dir(dest.parent)
    ensure_mirror(repo, dest)
    print(str(dest))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    mirror = Path(args.mirror).resolve()
    commits, branch = list_commits(mirror, args.branch)
    if args.format == "json":
        payload = [c.__dict__ for c in commits[: args.limit or None]]
        print(json.dumps({"branch": branch, "commits": payload}, ensure_ascii=False, indent=2))
        return 0
    # table
    limit = args.limit or len(commits)
    for i, c in enumerate(commits[:limit], start=1):
        print(f"{i:03d} {c.short} {c.datetime} {c.author} | {c.title}")
    return 0


def cmd_gen(args: argparse.Namespace) -> int:
    mirror = Path(args.mirror).resolve()
    out_root = Path(args.out).resolve()
    ensure_dir(out_root)
    commits, branch = list_commits(mirror, args.branch)
    if not commits:
        print("no commits found", file=sys.stderr)
        return 2
    limit = args.limit or len(commits)

    if args.style == "legacy":
        tip_sha = commits[-1].sha
        prev = None
        for i, curr in enumerate(commits[:limit], start=1):
            sbox = out_root / f"{i:03d}-{curr.short}"
            if sbox.exists() and not args.overwrite:
                if not args.quiet:
                    print(f"skip existing {sbox}")
                prev = curr
                continue
            path = generate_one_sbox_legacy(out_root, mirror, i, tip_sha, prev, curr, branch)
            if not args.quiet:
                print(f"OK {path}")
            prev = curr
    elif args.style == "head":
        # head style: take last N commits (most recent first)
        tail = commits[-limit:]
        seq = 1
        for idx in range(len(tail) - 1, -1, -1):
            # Iterate most recent first
            curr = tail[idx]
            prev = tail[idx - 1] if idx - 1 >= 0 else None
            prev_prev = tail[idx - 2] if idx - 2 >= 0 else None
            sbox = out_root / f"{seq:03d}-{curr.short}"
            if sbox.exists() and not args.overwrite:
                if not args.quiet:
                    print(f"skip existing {sbox}")
                seq += 1
                continue
            path = generate_one_sbox_headstyle(out_root, mirror, seq, prev_prev, prev, curr)
            if not args.quiet:
                print(f"OK {path}")
            seq += 1
    else:  # timeline
        # Generate for first-parent history oldest→newest; per commit include head/head-1/head-2 folders and diffs
        prev2 = None  # commit at i-2
        prev1 = None  # commit at i-1
        seq = 1
        for curr in commits[:limit]:
            sbox = out_root / f"{seq:03d}-{curr.short}"
            if sbox.exists() and not args.overwrite:
                if not args.quiet:
                    print(f"skip existing {sbox}")
                prev2, prev1 = prev1, curr
                seq += 1
                continue
            prev3 = None
            # prev3 = commit at i-3 is the previous of prev2; we don't have it unless we track history
            # We can reconstruct from commits list using index lookup; simpler approach: carry a rolling window
            # Keep a ring of last three commits
            # For current code flow, prev2 is i-2 and we don't have prev3; that's fine: we will write show(prev2) when prev3 is None
            path = generate_one_sbox_timeline(out_root, mirror, seq, curr, prev1, prev2, prev3)
            if not args.quiet:
                print(f"OK {path}")
            prev2, prev1 = prev1, curr
            seq += 1
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"not found: {root}", file=sys.stderr)
        return 2

    commit_dirs = [s for s in sorted(root.iterdir()) if s.is_dir()]
    total = len(commit_dirs)
    if total == 0:
        return 0

    # 并发策略：当目录数 > 2 时并发执行，线程数最多 100
    if total <= 2:
        bad = 0
        for s in commit_dirs:
            ok, msg = verify_sbox(s, strict=args.strict)
            status = "OK" if ok else "FAIL"
            print(f"{status} {s.name}: {msg}")
            if not ok:
                bad += 1
        return 0 if bad == 0 else 3

    max_workers = min(100, total)
    results: dict[str, tuple[bool, str]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        fut_map = {ex.submit(verify_sbox, s, args.strict): s for s in commit_dirs}
        for fut in as_completed(fut_map):
            s = fut_map[fut]
            ok, msg = fut.result()
            results[s.name] = (ok, msg)

    bad = 0
    # 打印时保持原始目录顺序
    for s in commit_dirs:
        ok, msg = results[s.name]
        status = "OK" if ok else "FAIL"
        print(f"{status} {s.name}: {msg}")
        if not ok:
            bad += 1
    return 0 if bad == 0 else 3


def cmd_clean(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not root.exists():
        return 0
    if not args.yes:
        print(f"Refuse to remove {root} without --yes", file=sys.stderr)
        return 1
    import shutil
    shutil.rmtree(root)
    print(f"removed {root}")
    return 0


def cmd_template_list(args: argparse.Namespace) -> int:
    names = list_templates(TEMPLATES_ROOT)
    for n in names:
        print(n)
    return 0


def cmd_template_copy(args: argparse.Namespace) -> int:
    dest = Path(args.to).resolve()
    if not dest.exists() or not dest.is_dir():
        print(f"destination not found: {dest}", file=sys.stderr)
        return 2
    copy_template(args.name, dest, TEMPLATES_ROOT, overwrite=args.overwrite)
    print(f"OK copied template '{args.name}' into {dest}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sboxgen", description="Generate reproducible Git sboxes")
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("mirror", help="create/update a local bare mirror")
    p.add_argument("--repo", required=True, help="Git repo URL or local path")
    p.add_argument("--dest", help="Destination mirror path (default .cache/mirrors/<name>.git)")
    p.set_defaults(func=cmd_mirror)

    p = sp.add_parser("list", help="list commits on a branch (first-parent, oldest→newest)")
    p.add_argument("--mirror", required=True, help="Path to a local bare mirror")
    p.add_argument("--branch", default="master", help="Branch to traverse")
    p.add_argument("--limit", type=int, default=0, help="limit number of commits")
    p.add_argument("--format", choices=["table", "json"], default="table")
    p.set_defaults(func=cmd_list)

    p = sp.add_parser("gen", help="generate sboxes for a branch (style: legacy|head|timeline)")
    p.add_argument("--mirror", required=True, help="Path to a local bare mirror")
    p.add_argument("--branch", default="master", help="Branch to traverse")
    p.add_argument("--out", default=".sboxes", help="Output root directory")
    p.add_argument("--limit", type=int, default=0, help="limit number of commits")
    p.add_argument("--overwrite", action="store_true", help="overwrite existing sboxes")
    p.add_argument("--quiet", action="store_true", help="less verbose output")
    p.add_argument("--style", choices=["legacy", "head", "timeline"], default="timeline", help="output style")
    p.set_defaults(func=cmd_gen)

    p = sp.add_parser("verify", help="verify generated sboxes structure and metadata")
    p.add_argument("--root", default=".sboxes", help="sboxes root directory")
    p.add_argument("--strict", action="store_true", help="strict checks (READY, name-seq match)")
    p.set_defaults(func=cmd_verify)

    p = sp.add_parser("clean", help="remove sboxes root")
    p.add_argument("--root", default=".sboxes", help="sboxes root directory")
    p.add_argument("--yes", action="store_true", help="confirm removal")
    p.set_defaults(func=cmd_clean)

    # template management
    pt = sp.add_parser("template", help="manage and apply templates to commit folders")
    st = pt.add_subparsers(dest="tcmd", required=True)

    ptl = st.add_parser("list", help="list available templates under .cache/templates")
    ptl.set_defaults(func=cmd_template_list)

    ptc = st.add_parser("copy", help="copy a template into a commit directory")
    ptc.add_argument("--name", required=True, help="template name")
    ptc.add_argument("--to", required=True, help="destination commit directory (e.g., .sboxes_timeline/001-xxxxxxx)")
    ptc.add_argument("--overwrite", action="store_true", help="overwrite existing files if present")
    ptc.set_defaults(func=cmd_template_copy)

    ptca = st.add_parser("copy-all", help="copy a template into all commit directories under a root")
    ptca.add_argument("--name", required=True, help="template name")
    ptca.add_argument("--root", required=True, help="sboxes root directory (e.g., .sboxes_timeline)")
    ptca.add_argument("--overwrite", action="store_true", help="overwrite existing files if present")
    def _copy_all(args: argparse.Namespace) -> int:
        root = Path(args.root).resolve()
        if not root.exists() or not root.is_dir():
            print(f"root not found: {root}", file=sys.stderr)
            return 2
        count = 0
        for sub in sorted(root.iterdir()):
            if not sub.is_dir():
                continue
            copy_template(args.name, sub, TEMPLATES_ROOT, overwrite=args.overwrite)
            count += 1
        print(f"OK copied template '{args.name}' into {count} directories under {root}")
        return 0
    ptca.set_defaults(func=_copy_all)

    # run over commits
    pr = sp.add_parser("run", help="apply template, execute scripts, and collect artifacts across commit dirs")
    pr.add_argument("--root", default=".sboxes_timeline", help="sboxes root directory")
    pr.add_argument("--template-name", help="template to apply to each dir (optional)")
    pr.add_argument("--apply-template", action="store_true", help="apply template before running")
    pr.add_argument("--overwrite-template", action="store_true", help="overwrite template files when applying")
    pr.add_argument("--no-exec", action="store_true", help="do not execute scripts")
    pr.add_argument("--collect-root", default=".artifacts", help="collect output root (reports/figs)")
    pr.add_argument("--no-collect-reports", action="store_true", help="do not collect report fragments")
    pr.add_argument("--collect-figs", action="store_true", help="collect figures (pdf) under figs/<commit>/")
    pr.add_argument("--quiet", action="store_true", help="less verbose output")
    def _run(args: argparse.Namespace) -> int:
        root = Path(args.root).resolve()
        if not root.exists() or not root.is_dir():
            print(f"not found: {root}", file=sys.stderr)
            return 2
        run_over_commits(
            root=root,
            template_name=args.template_name,
            apply_template=args.apply_template,
            overwrite_template=args.overwrite_template,
            exec_scripts=(not args.no_exec),
            collect_reports=(not args.no_collect_reports),
            collect_figs=args.collect_figs,
            collect_root=Path(args.collect_root).resolve() if args.collect_root else None,
            quiet=args.quiet,
        )
        print("OK run completed")
        return 0
    pr.set_defaults(func=_run)

    # codex exec helpers
    pc = sp.add_parser("codex", help="invoke codex exec for one or many commit directories")
    sc = pc.add_subparsers(dest="ccmd", required=True)

    pco = sc.add_parser("one", help="run codex exec for a single commit directory")
    pco.add_argument("--dir", required=True, help="commit directory path (e.g., .sboxes_timeline/001-xxxxxxx)")
    pco.add_argument("--dry-run", action="store_true", help="print command without executing")
    pco.add_argument("--no-save", action="store_true", help="do not save outputs to files")
    pco.add_argument("--timeout", type=int, default=0, help="timeout seconds")
    pco.add_argument("--api-key", help="override CODEX_API_KEY for this run; default reads env or .cache/codex_api_key")
    def _codex_one(args: argparse.Namespace) -> int:
        # Resolve API key precedence: arg > env > .cache/codex_api_key
        key = args.api_key or os.environ.get("CODEX_API_KEY")
        if not key:
            p = Path(".cache/codex_api_key")
            if p.exists():
                try:
                    key = p.read_text(encoding="utf-8").strip()
                except Exception:
                    key = None
        return codex_run_one(
            Path(args.dir),
            dry_run=args.dry_run,
            save_output=(not args.no_save),
            timeout_sec=(args.timeout or None),
            api_key=key,
        )
    pco.set_defaults(func=_codex_one)

    pcb = sc.add_parser("batch", help="run codex exec for all commit directories under a root")
    pcb.add_argument("--root", required=True, help="sboxes root directory (e.g., .sboxes_timeline)")
    pcb.add_argument("--limit", type=int, default=0, help="limit number of commit directories")
    pcb.add_argument("--dry-run", action="store_true", help="print commands without executing")
    pcb.add_argument("--no-save", action="store_true", help="do not save outputs to files")
    pcb.add_argument("--timeout", type=int, default=0, help="timeout seconds per commit")
    pcb.add_argument("--max-parallel", type=int, default=100, help="max parallel workers (default 100)")
    pcb.add_argument("--api-key", help="override CODEX_API_KEY for this run; default reads env or .cache/codex_api_key")
    def _codex_batch(args: argparse.Namespace) -> int:
        key = args.api_key or os.environ.get("CODEX_API_KEY")
        if not key:
            p = Path(".cache/codex_api_key")
            if p.exists():
                try:
                    key = p.read_text(encoding="utf-8").strip()
                except Exception:
                    key = None
        return codex_run_batch(
            Path(args.root),
            limit=args.limit,
            dry_run=args.dry_run,
            save_output=(not args.no_save),
            timeout_sec=(args.timeout or None),
            api_key=key,
            max_parallel=args.max_parallel,
        )
    pcb.set_defaults(func=_codex_batch)

    pcp = sc.add_parser("puml", help="use codex to compile and fix PlantUML in figs/*/algorithm_flow.puml across commits")
    pcp.add_argument("--root", required=True, help="sboxes root directory (e.g., .sboxes_timeline)")
    pcp.add_argument("--limit", type=int, default=0, help="limit number of commit directories")
    pcp.add_argument("--dry-run", action="store_true", help="print commands without executing")
    pcp.add_argument("--no-save", action="store_true", help="do not save outputs to files")
    pcp.add_argument("--timeout", type=int, default=0, help="timeout seconds per commit")
    pcp.add_argument("--max-parallel", type=int, default=100, help="max parallel workers (default 100)")
    pcp.add_argument("--api-key", help="override CODEX_API_KEY for this run; default reads env or .cache/codex_api_key")
    def _codex_puml(args: argparse.Namespace) -> int:
        key = args.api_key or os.environ.get("CODEX_API_KEY")
        if not key:
            p = Path(".cache/codex_api_key")
            if p.exists():
                try:
                    key = p.read_text(encoding="utf-8").strip()
                except Exception:
                    key = None
        return run_puml_batch(
            Path(args.root),
            limit=args.limit,
            dry_run=args.dry_run,
            save_output=(not args.no_save),
            timeout_sec=(args.timeout or None),
            api_key=key,
            max_parallel=args.max_parallel,
        )
    pcp.set_defaults(func=_codex_puml)

    # latex fix: run codex to fix xelatex build issues in collected artifacts
    pf = sp.add_parser("fixbug", help="use codex to fix xelatex compile errors under artifacts and generate PDF")
    pf.add_argument("--artifacts", default=".artifacts", help="artifacts root directory (where main.tex lives)")
    pf.add_argument("--tex", default="main.tex", help="tex file name inside artifacts root")
    pf.add_argument("--runs", type=int, default=3, help="times to run xelatex to stabilize references")
    pf.add_argument("--dry-run", action="store_true", help="print codex command without executing")
    pf.add_argument("--no-save", action="store_true", help="do not save codex outputs to files")
    pf.add_argument("--timeout", type=int, default=0, help="timeout seconds")
    pf.add_argument("--api-key", help="override CODEX_API_KEY for this run; default reads env or .cache/codex_api_key")
    def _fixbug(args: argparse.Namespace) -> int:
        # Resolve API key precedence: arg > env > .cache/codex_api_key
        key = args.api_key or os.environ.get("CODEX_API_KEY")
        if not key:
            p = Path(".cache/codex_api_key")
            if p.exists():
                try:
                    key = p.read_text(encoding="utf-8").strip()
                except Exception:
                    key = None
        artifacts = Path(args.artifacts).resolve()
        if not artifacts.exists() or not artifacts.is_dir():
            print(f"artifacts not found: {artifacts}", file=sys.stderr)
            return 2
        return run_latex_fix(
            artifacts_dir=artifacts,
            tex_name=args.tex,
            runs=args.runs,
            dry_run=args.dry_run,
            save_output=(not args.no_save),
            timeout_sec=(args.timeout or None),
            api_key=key,
        )
    pf.set_defaults(func=_fixbug)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
