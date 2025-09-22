#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import shlex
import signal
import threading
import subprocess
import shutil
import pty
import select
from pathlib import Path
from datetime import datetime
import time

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import queue
from typing import Optional, List, Dict
import re
import platform as _plat

# Import the isolated task executor
try:
    from isolated_task_executor import IsolatedTaskExecutor
except ImportError:
    IsolatedTaskExecutor = None

# Ensure we can import sboxgen.* when running from repo root
try:
    _SRC_PATH = str(Path(__file__).resolve().parents[1] / "src")
    if _SRC_PATH not in sys.path:
        sys.path.insert(0, _SRC_PATH)
except Exception:
    pass

# Lazy import; only used on macOS when embedding
GhosttyEmbedder = None  # default
try:
    # Case 1: running as script from tools/ directory
    from ghostty_embed import GhosttyEmbedder as _GE
    GhosttyEmbedder = _GE  # type: ignore
except Exception:
    try:
        # Case 2: running as package from repo root
        from tools.ghostty_embed import GhosttyEmbedder as _GE
        GhosttyEmbedder = _GE  # type: ignore
    except Exception:
        try:
            # Case 3: namespace package or other
            from .ghostty_embed import GhosttyEmbedder as _GE  # type: ignore
            GhosttyEmbedder = _GE
        except Exception:
            GhosttyEmbedder = None  # type: ignore


def _default_mirror_from_repo(repo: str) -> str:
    try:
        name = repo.rstrip("/")
        if name.endswith(".git"):
            name = name[:-4]
        name = name.split("/")[-1]
        return str(Path(".cache/mirrors") / f"{name}.git")
    except Exception:
        return str(Path(".cache/mirrors/repo.git"))


class SboxgenGUI:
    def __init__(self, master: tk.Tk):
        self.root = master
        self.root.title("CommitLens · 基于 Codex 的一站式提交报告生成器")
        self.root.geometry("980x820")
        self.root.minsize(820, 624)

        # state
        self.proc: Optional[subprocess.Popen] = None
        self.cancel_flag = False
        self.settings_path = Path(".cache/gui_settings.json")
        self.log_queue: queue.Queue = queue.Queue()
        self.ui_queue: queue.Queue = queue.Queue()  # (kind, *args)

        # vars
        self.repo_var = tk.StringVar(value="https://github.com/Formlabs/foxtrot.git")
        self.branch_var = tk.StringVar(value="master")
        self.limit_var = tk.IntVar(value=10)
        self.style_var = tk.StringVar(value="timeline")
        self.mirror_var = tk.StringVar(value=_default_mirror_from_repo(self.repo_var.get()))
        self.sboxes_root_var = tk.StringVar(value=str(Path(".sboxes")))
        self.sboxes_tex_var = tk.StringVar(value=str(Path(".sboxes_tex")))
        self.artifacts_root_var = tk.StringVar(value=str(Path(".artifacts")))
        self.timeout_var = tk.IntVar(value=6000)
        self.fix_runs_var = tk.IntVar(value=3)
        self.fix_force_var = tk.BooleanVar(value=True)
        self.max_parallel_var = tk.IntVar(value=100)
        self.codex_force_var = tk.BooleanVar(value=False)
        self.codex_runs_var = tk.IntVar(value=1)
        self.puml_force_var = tk.BooleanVar(value=False)
        self.puml_runs_var = tk.IntVar(value=1)
        self.api_key_var = tk.StringVar(value="")
        self.show_key_var = tk.BooleanVar(value=False)
        self.overwrite_reports_var = tk.BooleanVar(value=True)
        self.overwrite_figs_var = tk.BooleanVar(value=True)
        # UI: commit count display (for selected URL + branch)
        self.commit_count_var = tk.StringVar(value="分支提交总数：—")

        # 输出目录衍生/覆盖跟踪
        self._out_overridden = False
        try:
            self._last_derived_out = str((Path(".sboxes")).resolve())
        except Exception:
            self._last_derived_out = str(Path(".sboxes").resolve())

        # step status: pending → running → ok/fail
        self.steps = [
            {"key": "mirror", "label": "1) 镜像仓库 mirror", "status": tk.StringVar(value="pending")},
            {"key": "gen", "label": "2) 生成时间线 gen", "status": tk.StringVar(value="pending")},
            {"key": "verify", "label": "3) 校验生成 verify", "status": tk.StringVar(value="pending")},
            {"key": "codex", "label": "4) 批量 Codex 执行", "status": tk.StringVar(value="pending")},
            {"key": "collect_tex", "label": "5) 收集为 .sboxes_tex", "status": tk.StringVar(value="pending")},
            {"key": "texfix", "label": "6) 并行 PUML+LaTeX 修复（按提交）", "status": tk.StringVar(value="pending")},
            {"key": "fixbug", "label": "7) 汇总并生成 PDF", "status": tk.StringVar(value="pending")},
            {"key": "overwrite", "label": "8) 回写 artifacts → sboxes", "status": tk.StringVar(value="pending")},
        ]

        self._build_ui()
        self._bind_events()
        self._load_settings()
        self._refresh_styles()
        # 默认选择 timeline 作为当前风格
        try:
            self.style_var.set("timeline")
        except Exception:
            pass
        self._load_prompt_files()
        # Ensure README 模板区按当前风格（默认 timeline）加载
        try:
            self._on_style_change()
        except Exception:
            pass
        self._start_pollers()

    # ---------------- UI ----------------
    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        nb = ttk.Notebook(outer)
        nb.grid(row=0, column=0, sticky="nsew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        # tabs
        tab_basic = ttk.Frame(nb, padding=12)
        tab_codex = ttk.Frame(nb, padding=12)
        tab_readme = ttk.Frame(nb, padding=12)
        tab_run = ttk.Frame(nb, padding=12)
        tab_codex_output = ttk.Frame(nb, padding=12)
        tab_task_executor = ttk.Frame(nb, padding=12)  # 新增任务执行标签页
        tab_graph = ttk.Frame(nb, padding=12)  # 新增 Graph 标签页（原生绘制）
        nb.add(tab_basic, text="基本设置")
        nb.add(tab_codex, text="Codex 与参数")
        nb.add(tab_readme, text="README 模板")
        nb.add(tab_run, text="执行与日志")
        nb.add(tab_codex_output, text="Codex Output")
        nb.add(tab_task_executor, text="任务执行")  # 添加到标签栏
        nb.add(tab_graph, text="Graph")  # 任务图（原生绘制）

        # --- basic tab ---
        for i in range(8):
            tab_basic.rowconfigure(i, weight=0)
        tab_basic.columnconfigure(1, weight=1)

        ttk.Label(tab_basic, text="Git 仓库 URL:").grid(row=0, column=0, sticky="w", pady=6)
        e_repo = ttk.Entry(tab_basic, textvariable=self.repo_var)
        e_repo.grid(row=0, column=1, sticky="ew", padx=(8, 8), pady=6)
        ttk.Button(tab_basic, text="推断并刷新分支", command=self._autofill_and_update_branches_threaded).grid(row=0, column=2, pady=6)

        ttk.Label(tab_basic, text="分支:").grid(row=1, column=0, sticky="w", pady=6)
        self.branch_combo = ttk.Combobox(tab_basic, values=["master", "main"], textvariable=self.branch_var, state="readonly")
        self.branch_combo.grid(row=1, column=1, sticky="w", padx=(8, 8), pady=6)

        # commit count label (auto-updated on 推断镜像路径 / branch change)
        ttk.Label(tab_basic, textvariable=self.commit_count_var, foreground="#555").grid(row=1, column=2, sticky="w", padx=(16, 0))

        # move 提交数 limit to its own row
        ttk.Label(tab_basic, text="提交数 limit:").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Spinbox(tab_basic, from_=1, to=200, textvariable=self.limit_var, width=8).grid(row=2, column=1, sticky="w", padx=(8, 0), pady=6)

        ttk.Label(tab_basic, text="风格 (模板):").grid(row=3, column=0, sticky="w", pady=6)
        self.style_combo = ttk.Combobox(tab_basic, values=[], textvariable=self.style_var, state="readonly")
        self.style_combo.grid(row=3, column=1, sticky="w", padx=(8, 8), pady=6)

        ttk.Label(tab_basic, text="镜像路径 mirror:").grid(row=4, column=0, sticky="w", pady=6)
        e_mirror = ttk.Entry(tab_basic, textvariable=self.mirror_var)
        e_mirror.grid(row=4, column=1, sticky="ew", padx=(8, 8), pady=6)
        ttk.Button(tab_basic, text="浏览", command=self._browse_mirror).grid(row=4, column=2, pady=6)

        ttk.Label(tab_basic, text="时间线根目录 out:").grid(row=5, column=0, sticky="w", pady=6)
        e_out = ttk.Entry(tab_basic, textvariable=self.sboxes_root_var)
        e_out.grid(row=5, column=1, sticky="ew", padx=(8, 8), pady=6)
        ttk.Button(tab_basic, text="浏览", command=self._browse_out).grid(row=5, column=2, pady=6)
        e_out.bind('<KeyRelease>', lambda e: setattr(self, '_out_overridden', True))

        ttk.Label(tab_basic, text="TEX 时间线根目录 (收集输出):").grid(row=6, column=0, sticky="w", pady=6)
        e_out_tex = ttk.Entry(tab_basic, textvariable=self.sboxes_tex_var)
        e_out_tex.grid(row=6, column=1, sticky="ew", padx=(8, 8), pady=6)
        ttk.Button(tab_basic, text="浏览", command=self._browse_out_tex).grid(row=6, column=2, pady=6)

        ttk.Label(tab_basic, text="产物目录 artifacts:").grid(row=7, column=0, sticky="w", pady=6)
        e_art = ttk.Entry(tab_basic, textvariable=self.artifacts_root_var)
        e_art.grid(row=7, column=1, sticky="ew", padx=(8, 8), pady=6)
        ttk.Button(tab_basic, text="浏览", command=self._browse_artifacts).grid(row=7, column=2, pady=6)

        # --- codex tab ---
        for i in range(8):
            tab_codex.rowconfigure(i, weight=0)
        tab_codex.columnconfigure(1, weight=1)

        # moved: 参数转移至“执行与日志”页

        # 说明文字已移除（原为“使用 README 的 6 步流水 …”）

        # 第4步：批量 Codex 执行 提示词
        lf_codex = ttk.LabelFrame(tab_codex, text="第4步 · 批量 Codex 执行 提示词（支持占位符：{dir}）", padding=8)
        lf_codex.grid(row=3, column=0, columnspan=4, sticky="nsew", pady=(8, 4))
        lf_codex.columnconfigure(0, weight=1)
        self.codex_prompt_editor = scrolledtext.ScrolledText(lf_codex, height=10)
        self.codex_prompt_editor.grid(row=0, column=0, sticky="nsew")
        bar1 = ttk.Frame(lf_codex)
        bar1.grid(row=1, column=0, sticky="e", pady=(6, 0))
        ttk.Button(bar1, text="重置默认", command=self._reset_codex_prompt).pack(side=tk.LEFT)
        ttk.Button(bar1, text="保存到 .cache/codex_prompt.txt", command=self._save_codex_prompt).pack(side=tk.LEFT, padx=(8, 0))

        # 第7步：LaTeX 修复（汇总）提示词（用于 fixbug）
        lf_latex = ttk.LabelFrame(tab_codex, text="第7步 · LaTeX 修复（汇总）提示词（用于 fixbug；支持占位符：{dir} {tex} {runs}）", padding=8)
        lf_latex.grid(row=5, column=0, columnspan=4, sticky="nsew", pady=(8, 0))
        lf_latex.columnconfigure(0, weight=1)
        self.latex_prompt_editor = scrolledtext.ScrolledText(lf_latex, height=8)
        self.latex_prompt_editor.grid(row=0, column=0, sticky="nsew")
        bar2 = ttk.Frame(lf_latex)
        bar2.grid(row=1, column=0, sticky="e", pady=(6, 0))
        ttk.Button(bar2, text="重置默认", command=self._reset_latex_prompt).pack(side=tk.LEFT)
        ttk.Button(bar2, text="保存到 .cache/latex_fix_prompt.txt", command=self._save_latex_prompt).pack(side=tk.LEFT, padx=(8, 0))

        # 第6步：PUML + LaTeX 并行修复 提示词（用于 tex-fix）
        lf_texfix = ttk.LabelFrame(tab_codex, text="第6步 · PUML + LaTeX 并行修复 提示词（用于 tex-fix；支持占位符：{dir} {tex} {runs}）", padding=8)
        lf_texfix.grid(row=4, column=0, columnspan=4, sticky="nsew", pady=(8, 0))
        lf_texfix.columnconfigure(0, weight=1)
        self.tex_fix_prompt_editor = scrolledtext.ScrolledText(lf_texfix, height=8)
        self.tex_fix_prompt_editor.grid(row=0, column=0, sticky="nsew")
        bar2sx = ttk.Frame(lf_texfix)
        bar2sx.grid(row=1, column=0, sticky="e", pady=(6, 0))
        ttk.Button(bar2sx, text="重置默认", command=self._reset_tex_fix_prompt).pack(side=tk.LEFT)
        ttk.Button(bar2sx, text="保存到 .cache/tex_fix_prompt.txt", command=self._save_tex_fix_prompt).pack(side=tk.LEFT, padx=(8, 0))

        # 预留空白行以便布局（原高级分块已合并，不再展示）
        ttk.Frame(tab_codex).grid(row=6, column=0, sticky="nsew", pady=(4, 0))
        ttk.Frame(tab_codex).grid(row=7, column=0, sticky="nsew", pady=(4, 0))

        # --- README template tab ---
        # Make editor area take ~90% height: row 1 gets higher weight
        tab_readme.rowconfigure(0, weight=0)
        tab_readme.rowconfigure(1, weight=9)
        tab_readme.columnconfigure(0, weight=1)
        # Style selector row in README tab (browse styles)
        style_sel = ttk.Frame(tab_readme)
        style_sel.grid(row=0, column=0, sticky="ew")
        style_sel.columnconfigure(1, weight=1)
        ttk.Label(style_sel, text="当前风格:").grid(row=0, column=0, sticky="w")
        self.style_combo_readme = ttk.Combobox(style_sel, textvariable=self.style_var, state="readonly")
        self.style_combo_readme.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(style_sel, text="新建风格", command=self._new_style).grid(row=0, column=2)
        ttk.Button(style_sel, text="删除风格", command=self._delete_style).grid(row=0, column=3, padx=(8, 0))

        tmpl_frame = ttk.LabelFrame(tab_readme, text="README 模板（所有提交目录共用；支持占位符：{seq} {seq_str} {short} {sha} {title} {author} {datetime} {prev_sha} {prev_short}）", padding=8)
        tmpl_frame.grid(row=1, column=0, sticky="nsew")
        tmpl_frame.rowconfigure(0, weight=1)
        tmpl_frame.columnconfigure(0, weight=1)
        self.readme_template_editor = scrolledtext.ScrolledText(tmpl_frame, height=10)
        self.readme_template_editor.grid(row=0, column=0, sticky="nsew")
        tbar = ttk.Frame(tmpl_frame)
        tbar.grid(row=1, column=0, sticky="e")
        ttk.Button(tbar, text="重置为当前默认", command=self._reset_readme_template_default).pack(side=tk.LEFT)
        ttk.Button(tbar, text="保存当前风格", command=self._save_readme_template).pack(side=tk.LEFT, padx=(8, 0))

        # --- run tab ---
        tab_run.rowconfigure(3, weight=1)
        tab_run.columnconfigure(0, weight=1)

        steps_frame = ttk.LabelFrame(tab_run, text="执行步骤", padding=10)
        steps_frame.grid(row=0, column=0, sticky="ew")
        steps_frame.columnconfigure(2, weight=1)

        self.step_widgets = {}
        for idx, s in enumerate(self.steps):
            row = idx
            lbl = ttk.Label(steps_frame, text=s["label"], width=32)
            lbl.grid(row=row, column=0, sticky="w", pady=4)
            stv = ttk.Label(steps_frame, textvariable=self._status_text_var(s["status"]))
            stv.grid(row=row, column=1, sticky="w")
            # Per-step controls in the steps table, left of the Run button
            if s["key"] == "codex":
                cell = ttk.Frame(steps_frame)
                cell.grid(row=row, column=2, sticky="w")
                ttk.Label(cell, text="运行次数:").pack(side=tk.LEFT)
                ttk.Spinbox(cell, from_=1, to=10, textvariable=self.codex_runs_var, width=6).pack(side=tk.LEFT, padx=(4, 12))
                ttk.Checkbutton(cell, text="强制重跑（删 error/status）", variable=self.codex_force_var).pack(side=tk.LEFT)
            elif s["key"] == "collect_tex":
                # Overwrite option for collection
                self.collect_tex_overwrite_var = getattr(self, 'collect_tex_overwrite_var', tk.BooleanVar(value=True))
                cell = ttk.Frame(steps_frame)
                cell.grid(row=row, column=2, sticky="w")
                ttk.Checkbutton(cell, text="覆盖已有", variable=self.collect_tex_overwrite_var).pack(side=tk.LEFT)
            elif s["key"] == "texfix":
                cell = ttk.Frame(steps_frame)
                cell.grid(row=row, column=2, sticky="w")
                ttk.Label(cell, text="运行次数:").pack(side=tk.LEFT)
                ttk.Spinbox(cell, from_=1, to=10, textvariable=self.puml_runs_var, width=6).pack(side=tk.LEFT, padx=(4, 12))
                ttk.Checkbutton(cell, text="强制重跑（删 error/status）", variable=self.puml_force_var).pack(side=tk.LEFT)
            elif s["key"] == "fixbug":
                cell = ttk.Frame(steps_frame)
                cell.grid(row=row, column=2, sticky="w")
                ttk.Label(cell, text="运行次数:").pack(side=tk.LEFT)
                ttk.Spinbox(cell, from_=1, to=10, textvariable=self.fix_runs_var, width=6).pack(side=tk.LEFT, padx=(4, 12))
                ttk.Checkbutton(cell, text="强制重跑（删 error/status）", variable=self.fix_force_var).pack(side=tk.LEFT)
            elif s["key"] == "overwrite":
                # Options for overwrite step: choose which kinds to copy back
                cell = ttk.Frame(steps_frame)
                cell.grid(row=row, column=2, sticky="w")
                ttk.Checkbutton(cell, text="覆盖报告(reports)", variable=self.overwrite_reports_var).pack(side=tk.LEFT)
                ttk.Checkbutton(cell, text="覆盖图示(figs)", variable=self.overwrite_figs_var).pack(side=tk.LEFT, padx=(12, 0))
            btn = ttk.Button(steps_frame, text="运行", command=lambda k=s["key"]: self._run_step_threaded(k))
            # Place the run button in the rightmost column
            btn.grid(row=row, column=3, sticky="e")
            self.step_widgets[s["key"]] = {"label": lbl, "status": stv, "button": btn}

        actions = ttk.Frame(tab_run)
        actions.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        ttk.Button(actions, text="一键执行全部", command=self._run_all_threaded).pack(side=tk.LEFT)
        ttk.Button(actions, text="取消当前执行", command=self._cancel_current).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="清空日志", command=self._clear_log).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="清空历史并备份", command=self._backup_current_history_threaded).pack(side=tk.LEFT, padx=(8, 0))

        # params row: execution parameters (global)
        params = ttk.Frame(tab_run)
        params.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        params.columnconfigure(1, weight=1)

        ttk.Label(params, text="超时(秒):").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(params, from_=60, to=36000, textvariable=self.timeout_var, width=10).grid(row=0, column=1, sticky="w", padx=(8, 16))

        ttk.Label(params, text="最大并发数:").grid(row=0, column=2, sticky="e")
        ttk.Spinbox(params, from_=1, to=512, textvariable=self.max_parallel_var, width=6).grid(row=0, column=3, sticky="w", padx=(8, 0))

        ttk.Label(params, text="OpenAI/Codex API Key:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.api_entry = ttk.Entry(params, textvariable=self.api_key_var, show="*")
        self.api_entry.grid(row=1, column=1, columnspan=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        ttk.Button(params, text="显示/隐藏", command=self._toggle_key).grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Button(params, text="保存至 .cache/codex_api_key", command=self._save_key).grid(row=1, column=3, sticky="w", padx=(8, 0), pady=(8, 0))

        log_frame = ttk.LabelFrame(tab_run, text="执行日志", padding=10)
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=18)
        self.log_text.grid(row=0, column=0, sticky="nsew")

        status_bar = ttk.Frame(tab_run)
        status_bar.grid(row=4, column=0, sticky="ew")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status_bar, textvariable=self.status_var).pack(side=tk.LEFT)

        # --- codex output viewer tab ---
        self._build_codex_output_tab(tab_codex_output)

        # --- task executor tab ---
        self._build_task_executor_tab(tab_task_executor)
        self._build_graph_tab(tab_graph)

    def _bind_events(self):
        self.repo_var.trace_add("write", lambda *_: self._maybe_update_mirror())
        self.style_var.trace_add("write", lambda *_: self._on_style_change())
        # Update commit count when branch changes (after mirror is inferred/fetched)
        try:
            self.branch_combo.bind('<<ComboboxSelected>>', lambda e: self._update_branch_commit_count_threaded())
        except Exception:
            pass
        # Also refresh branch list when repo or mirror path changes (without updating remotes)
        self.repo_var.trace_add("write", lambda *_: self._refresh_branches_threaded(update=False))
        self.mirror_var.trace_add("write", lambda *_: self._refresh_branches_threaded(update=False))

    # ---------------- settings ----------------
    def _load_settings(self):
        try:
            if self.settings_path.exists():
                data = json.loads(self.settings_path.read_text(encoding="utf-8"))
                self.repo_var.set(data.get("repo", self.repo_var.get()))
                self.branch_var.set(data.get("branch", self.branch_var.get()))
                self.limit_var.set(int(data.get("limit", self.limit_var.get())))
                self.style_var.set(data.get("style", self.style_var.get()))
                self.mirror_var.set(data.get("mirror", self.mirror_var.get()))
                self.sboxes_root_var.set(data.get("sboxes_root", self.sboxes_root_var.get()))
                self.sboxes_tex_var.set(data.get("sboxes_tex", self.sboxes_tex_var.get()))
                self.artifacts_root_var.set(data.get("artifacts_root", self.artifacts_root_var.get()))
                self.timeout_var.set(int(data.get("timeout", self.timeout_var.get())))
                # Back-compat: read both 'fix_runs' and legacy 'runs'
                self.fix_runs_var.set(int(data.get("fix_runs", data.get("runs", self.fix_runs_var.get()))))
                self.fix_force_var.set(bool(data.get("fix_force", self.fix_force_var.get())))
                self.codex_force_var.set(bool(data.get("codex_force", self.codex_force_var.get())))
                self.puml_force_var.set(bool(data.get("puml_force", self.puml_force_var.get())))
                self.codex_runs_var.set(int(data.get("codex_runs", self.codex_runs_var.get())))
                self.puml_runs_var.set(int(data.get("puml_runs", self.puml_runs_var.get())))
                self.max_parallel_var.set(int(data.get("max_parallel", self.max_parallel_var.get())))
                # Load task executor timeout setting (新增)
                if hasattr(self, 'task_timeout_var'):
                    self.task_timeout_var.set(int(data.get("task_timeout", 6000)))
        except Exception:
            pass

        # load api key if present
        try:
            p = Path(".cache/codex_api_key")
            if p.exists():
                self.api_key_var.set(p.read_text(encoding="utf-8").strip())
        except Exception:
            pass

    def _save_settings(self):
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "repo": self.repo_var.get(),
                "branch": self.branch_var.get(),
                "limit": int(self.limit_var.get()),
                "style": self.style_var.get(),
                "mirror": self.mirror_var.get(),
                "sboxes_root": self.sboxes_root_var.get(),
                "sboxes_tex": self.sboxes_tex_var.get(),
                "artifacts_root": self.artifacts_root_var.get(),
                "timeout": int(self.timeout_var.get()),
                # Write both for back-compat
                "runs": int(self.fix_runs_var.get()),
                "fix_runs": int(self.fix_runs_var.get()),
                "fix_force": bool(self.fix_force_var.get()),
                "codex_force": bool(self.codex_force_var.get()),
                "puml_force": bool(self.puml_force_var.get()),
                "codex_runs": int(self.codex_runs_var.get()),
                "puml_runs": int(self.puml_runs_var.get()),
                "max_parallel": int(self.max_parallel_var.get()),
                # Task executor timeout setting (新增)
                "task_timeout": int(self.task_timeout_var.get()) if hasattr(self, 'task_timeout_var') else 6000,
            }
            self.settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---------------- helpers ----------------
    def _autofill_mirror(self):
        self.mirror_var.set(_default_mirror_from_repo(self.repo_var.get()))
        # After inferring mirror path, fetch commit count for selected URL+branch
        try:
            self._update_branch_commit_count_threaded()
        except Exception:
            pass
        # Try populate branch list from local mirror (no fetch here)
        try:
            self._refresh_branches_threaded(update=False)
        except Exception:
            pass

    def _autofill_and_update_branches_threaded(self):
        # Set mirror path on main thread for UI consistency
        self._autofill_mirror()
        # Then update all branches in background
        threading.Thread(target=self._autofill_and_update_branches, daemon=True).start()

    def _autofill_and_update_branches(self):
        repo = (self.repo_var.get() or "").strip()
        mirror = Path(self.mirror_var.get() or _default_mirror_from_repo(repo)).resolve()
        try:
            from sboxgen.gitio import ensure_mirror, update_all_branches  # type: ignore
        except Exception as e:
            self._append_log(f"[分支] 导入模块失败：{e}")
            return
        try:
            if (mirror / "HEAD").exists():
                self._append_log("[分支] 正在更新全部分支（mirror fetch）…")
                update_all_branches(mirror, repo_url=(repo or None))
            else:
                if not repo:
                    self._append_log("[分支] 未配置 URL，无法创建 mirror。")
                    return
                self._append_log("[分支] 正在创建 mirror（包含全部分支）…")
                ensure_mirror(repo, mirror)
            # Refresh branch list (no further fetch) and update count for current selection
            self._refresh_branches(update=False)
            self._update_branch_commit_count_threaded()
        except Exception as e:
            self._append_log(f"[分支] 更新失败：{e}")

    def _update_branch_commit_count_threaded(self):
        # run in background to avoid blocking UI
        self.commit_count_var.set("分支提交总数：统计中…")
        threading.Thread(target=self._update_branch_commit_count, daemon=True).start()

    def _update_branch_commit_count(self):
        repo = (self.repo_var.get() or "").strip()
        branch = (self.branch_var.get() or "master").strip()
        if not repo:
            self.ui_queue.put(("commit_count", "分支提交总数：未配置 URL"))
            return
        try:
            from sboxgen.gitio import count_commits_fast  # type: ignore
        except Exception as e:
            self.ui_queue.put(("commit_count", "分支提交总数：统计失败（导入）"))
            try:
                self._append_log(f"[统计失败] 导入模块失败：{e}")
            except Exception:
                pass
            return
        # Only read from existing mirror to stay fast (no fetch)
        mirror = Path(self.mirror_var.get() or _default_mirror_from_repo(repo)).resolve()
        if not (mirror / "HEAD").exists():
            self.ui_queue.put(("commit_count", "分支提交总数：未找到镜像（先执行第1步或指定已有镜像路径）"))
            return
        try:
            total, resolved_branch = count_commits_fast(mirror, branch)
            self.ui_queue.put(("commit_count", f"分支提交总数：{total}（{resolved_branch}）"))
            self._append_log(f"[统计] {resolved_branch} 分支共有 {total} 个 commits（本地 mirror，仅 first-parent）")
        except Exception as e:
            self.ui_queue.put(("commit_count", "分支提交总数：统计失败"))
            try:
                self._append_log(f"[统计失败] 无法获取提交数：{e}")
            except Exception:
                pass

    def _refresh_branches_threaded(self, update: bool = False):
        threading.Thread(target=self._refresh_branches, args=(update,), daemon=True).start()

    def _refresh_branches(self, update: bool = False):
        repo = (self.repo_var.get() or "").strip()
        mirror = Path(self.mirror_var.get() or _default_mirror_from_repo(repo)).resolve()
        if not repo and not (mirror / "HEAD").exists():
            return
        try:
            from sboxgen.gitio import list_local_branches, update_all_branches, ensure_mirror  # type: ignore
        except Exception as e:
            self._append_log(f"[分支刷新失败] 导入模块失败：{e}")
            return
        try:
            if update:
                if not (mirror / "HEAD").exists():
                    # Create full mirror first if absent
                    if repo:
                        self._append_log("[分支] 正在 clone mirror（全部分支）…")
                        ensure_mirror(repo, mirror)
                # Update all branches (prune) using origin
                self._append_log("[分支] 正在更新全部分支（remote update --prune）…")
                update_all_branches(mirror, repo_url=(repo or None))
            names = list_local_branches(mirror)
            if not names:
                self._append_log("[分支] 未发现任何分支（mirror 不存在或为空）。")
                return
            # Update combobox values in UI thread via queue
            self.ui_queue.put(("branches", names))
            # If current selection not in list, select a reasonable default
            cur = self.branch_var.get().strip()
            pick = None
            if cur in names:
                pick = cur
            elif "master" in names:
                pick = "master"
            elif "main" in names:
                pick = "main"
            else:
                pick = names[0]
            if pick:
                self.ui_queue.put(("branch_select", pick))
                # Also refresh count for selected
                self._update_branch_commit_count_threaded()
        except Exception as e:
            self._append_log(f"[分支刷新失败] {e}")

    def _maybe_update_mirror(self):
        # if mirror path is still the default for previous repo, update
        cur = Path(self.mirror_var.get()).name
        if cur in ("repo.git", ""):
            self._autofill_mirror()

    def _browse_mirror(self):
        path = filedialog.asksaveasfilename(title="选择/创建镜像路径", defaultextension=".git", initialfile=Path(self.mirror_var.get()).name)
        if path:
            self.mirror_var.set(path)

    def _browse_out(self):
        path = filedialog.askdirectory(title="选择时间线根目录")
        if path:
            self.sboxes_root_var.set(path)
            # optional: could rescan dirs if needed for template derivation
            self._out_overridden = True
            try:
                self._refresh_chain_total()
            except Exception:
                pass

    def _browse_out_tex(self):
        path = filedialog.askdirectory(title="选择 TEX 时间线根目录")
        if path:
            self.sboxes_tex_var.set(path)

    def _browse_artifacts(self):
        path = filedialog.askdirectory(title="选择产物目录")
        if path:
            self.artifacts_root_var.set(path)

    def _toggle_key(self):
        self.show_key_var.set(not self.show_key_var.get())
        self.api_entry.config(show="" if self.show_key_var.get() else "*")

    def _save_key(self):
        try:
            Path(".cache").mkdir(parents=True, exist_ok=True)
            Path(".cache/codex_api_key").write_text(self.api_key_var.get().strip(), encoding="utf-8")
            messagebox.showinfo("保存成功", "API Key 已写入 .cache/codex_api_key")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _status_text_var(self, status_var: tk.StringVar) -> tk.StringVar:
        out = tk.StringVar()

        def refresh(*_):
            s = status_var.get()
            if s == "pending":
                out.set("待执行 ⏳")
            elif s == "running":
                out.set("执行中 🟡")
            elif s == "ok":
                out.set("成功 ✅")
            elif s == "fail":
                out.set("失败 ❌")
            else:
                out.set(s)

        status_var.trace_add("write", refresh)
        refresh()
        return out

    def _append_log(self, text: str):
        # enqueue for main-thread update
        self.log_queue.put(text)

    def _set_status(self, text: str):
        # enqueue
        self.ui_queue.put(("status", text))

    def _clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def _cancel_current(self):
        self.cancel_flag = True
        if self.proc and self.proc.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                else:
                    self.proc.terminate()
                self._append_log("🛑 已请求终止当前子进程")
            except Exception as e:
                self._append_log(f"终止失败: {e}")

    # ---------------- execution ----------------
    def _run_step_threaded(self, key: str):
        # set running status in main thread first
        step = next(s for s in self.steps if s["key"] == key)
        step["status"].set("running")
        threading.Thread(target=self._run_step, args=(key,), daemon=True).start()

    def _run_all_threaded(self):
        threading.Thread(target=self._run_all, daemon=True).start()

    def _run_all(self):
        self._save_settings()
        self._reset_all_status()
        for s in self.steps:
            if self.cancel_flag:
                break
            # mark running, then run
            s["status"].set("running")
            ok = self._run_step(s["key"])  # run inline to keep sequence
            if not ok:
                break

    def _reset_all_status(self):
        for s in self.steps:
            s["status"].set("pending")
        self.cancel_flag = False

    def _build_env(self):
        env = os.environ.copy()
        key = (self.api_key_var.get() or "").strip()
        if key:
            env["CODEX_API_KEY"] = key
        # ensure src is on path so `-m sboxgen.cli` works from repo
        src_path = str(Path(__file__).resolve().parents[1] / "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")

        # pass prompt overrides if provided
        codex_prompt = getattr(self, 'codex_prompt_editor', None)
        if codex_prompt is not None:
            codex_text = self._get_editor_text(codex_prompt).strip()
            if codex_text:
                env["SBOXGEN_CODEX_PROMPT"] = codex_text
        latex_prompt = getattr(self, 'latex_prompt_editor', None)
        if latex_prompt is not None:
            latex_text = self._get_editor_text(latex_prompt).strip()
            if latex_text:
                env["SBOXGEN_CODEX_LATEX_PROMPT"] = latex_text
                # 用同一文本覆盖 shards 变量，保证 fixbug 也能拿到
                env["SBOXGEN_CODEX_LATEX_SHARDS_PROMPT"] = latex_text
        # Combined PUML+LaTeX prompt for tex-fix
        try:
            tfp = getattr(self, 'tex_fix_prompt_editor', None)
            if tfp is not None:
                tfp_text = self._get_editor_text(tfp).strip()
                if tfp_text:
                    env["SBOXGEN_CODEX_TEX_FIX_PROMPT"] = tfp_text
        except Exception:
            pass
        # README 模板绑定到“风格”：优先样式文件，其次编辑器文本
        try:
            f = self._style_file_path(self.style_var.get())
            if f and f.exists():
                env["SBOXGEN_SBOX_README_TEMPLATE_FILE"] = str(f.resolve())
            else:
                readme_tmpl = getattr(self, 'readme_template_editor', None)
                if readme_tmpl is not None:
                    readme_text = self._get_editor_text(readme_tmpl).strip()
                    if readme_text:
                        env["SBOXGEN_SBOX_README_TEMPLATE"] = readme_text
        except Exception:
            pass
        # 不再单独注入 PUML/LaTeX shards 提示词（已合并）
        return env

    def _popen_stream(self, cmd: list[str], cwd: Optional[Path] = None) -> int:
        self._append_log("$ " + " ".join(shlex.quote(x) for x in cmd))
        self._set_status("运行中…")
        try:
            # create process group to allow group terminate
            preexec = os.setsid if os.name == "posix" else None
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(cwd) if cwd else None,
                env=self._build_env(),
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                universal_newlines=True,
                preexec_fn=preexec,
            )
            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                self._append_log(line.rstrip())
            rc = self.proc.wait()
            return rc
        except FileNotFoundError:
            self._append_log("未找到 Python 解释器或命令。")
            return 127
        except Exception as e:
            self._append_log(f"执行错误: {e}")
            return 1
        finally:
            self.proc = None

    def _python_cmd(self, *args: str) -> list[str]:
        return [sys.executable, "-m", "sboxgen.cli", *args]

    def _run_step(self, key: str) -> bool:
        step = next(s for s in self.steps if s["key"] == key)
        ok = False

        repo = self.repo_var.get().strip()
        branch = self.branch_var.get().strip()
        limit = int(self.limit_var.get())
        style = self.style_var.get().strip()
        mirror = self.mirror_var.get().strip()
        out_root = self.sboxes_root_var.get().strip()
        out_tex_root = self.sboxes_tex_var.get().strip()
        artifacts = self.artifacts_root_var.get().strip()
        timeout = int(self.timeout_var.get())
        runs = int(self.fix_runs_var.get())

        Path(mirror).parent.mkdir(parents=True, exist_ok=True)
        Path(out_root).mkdir(parents=True, exist_ok=True)
        Path(artifacts).mkdir(parents=True, exist_ok=True)

        if key == "mirror":
            cmd = self._python_cmd(
                "mirror", "--repo", repo, "--dest", mirror
            )
        elif key == "gen":
            cmd = self._python_cmd(
                # 结构固定（统一 head/head-1/head-2），风格仅用于 README 模板
                "gen", "--mirror", mirror, "--branch", branch, "--out", out_root,
                "--limit", str(limit), "--overwrite", "--style", self.style_var.get().strip()
            )
        elif key == "verify":
            cmd = self._python_cmd("verify", "--root", out_root, "--strict")
        elif key == "codex":
            args = [
                "codex", "batch", "--root", out_root, "--limit", str(limit),
                "--timeout", str(timeout), "--max-parallel", str(int(self.max_parallel_var.get() or 0) or 1),
                "--runs", str(int(self.codex_runs_var.get() or 1))
            ]
            if self.codex_force_var.get():
                args.append("--force")
            cmd = self._python_cmd(*args)
        elif key == "collect_tex":
            args = [
                "collect-tex", "--from-root", out_root, "--to-root", out_tex_root
            ]
            if getattr(self, 'collect_tex_overwrite_var', None) and self.collect_tex_overwrite_var.get():
                args.append("--overwrite")
            cmd = self._python_cmd(*args)
        elif key == "texfix":
            # Step 6: parallel PUML+LaTeX fix inside .sboxes_tex
            args = [
                "tex-fix", "--root", out_tex_root, "--limit", str(limit),
                "--timeout", str(timeout), "--max-parallel", str(int(self.max_parallel_var.get() or 0) or 1),
                "--runs", str(int(self.puml_runs_var.get() or 1))
            ]
            if self.puml_force_var.get():
                args.append("--force")
            cmd = self._python_cmd(*args)
        elif key == "fixbug":
            # Step 7: collect from .sboxes_tex into .artifacts, then fix main.tex
            # 7.1 collect reports+figs into artifacts
            cmd = self._python_cmd(
                "run", "--root", out_tex_root, "--collect-root", artifacts, "--collect-figs", "--no-exec"
            )
            rc = self._popen_stream(cmd)
            if rc != 0:
                self.ui_queue.put(("step", key, "fail"))
                self._set_status(f"{step['label']}（收集阶段）失败，返回码 {rc}")
                return False
            # 7.2 fix main.tex under artifacts
            args = [
                "fixbug", "--artifacts", artifacts, "--tex", "main.tex", "--runs", str(runs), "--timeout", str(timeout)
            ]
            if self.fix_force_var.get():
                args.append("--force")
            cmd = self._python_cmd(*args)
        elif key == "overwrite":
            # Step 8: overwrite artifacts back into sboxes timeline
            args = [
                "overwrite", "--artifacts", artifacts, "--root", out_root
            ]
            if not self.overwrite_reports_var.get():
                args.append("--no-reports")
            if not self.overwrite_figs_var.get():
                args.append("--no-figs")
            cmd = self._python_cmd(*args)
        else:
            self._append_log(f"未知步骤: {key}")
            step["status"].set("fail")
            return False

        rc = self._popen_stream(cmd)
        ok = (rc == 0)
        # push UI updates
        self.ui_queue.put(("step", key, "ok" if ok else "fail"))
        self._set_status(f"{step['label']} 完成，返回码 {rc}")
        # gen 以外的步骤这里统一返回 ok
        return ok

    # ---------------- polling (UI thread) ----------------
    def _start_pollers(self):
        self.root.after(100, self._drain_queues)

    def _drain_queues(self):
        # logs
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, line + "\n")
                self.log_text.see(tk.END)
        except queue.Empty:
            pass

        # ui signals
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                kind = msg[0]
                if kind == "status":
                    self.status_var.set(msg[1])
                elif kind == "step":
                    key, val = msg[1], msg[2]
                    step = next(s for s in self.steps if s["key"] == key)
                    step["status"].set(val)
                elif kind == "commit_count":
                    try:
                        self.commit_count_var.set(msg[1])
                    except Exception:
                        pass
                elif kind == "ghostty_out":
                    # Append text to the simple terminal area
                    try:
                        self.ghostty_text.insert(tk.END, msg[1])
                        self.ghostty_text.see(tk.END)
                    except Exception:
                        pass
                elif kind == "branches":
                    try:
                        names = msg[1]
                        self.branch_combo["values"] = names
                    except Exception:
                        pass
                elif kind == "branch_select":
                    try:
                        self.branch_var.set(msg[1])
                    except Exception:
                        pass
        except queue.Empty:
            pass

        self.root.after(100, self._drain_queues)

    # ---------------- Ghostty embedding (libghostty) ----------------
    # ---------------- Codex Output Viewer Methods ----------------
    def _build_codex_output_tab(self, tab):
        """构建 Codex Output 查看器标签页"""
        tab.rowconfigure(2, weight=1)  # 主显示区域
        tab.columnconfigure(0, weight=1)

        # 初始化消息位置映射
        self.codex_message_positions = {}  # {index: (start_line, end_line)}

        # 顶部控制栏 - 文件/文件夹选择
        control_frame = ttk.LabelFrame(tab, text="文件夹选择与监控", padding=10)
        control_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        control_frame.columnconfigure(1, weight=1)

        ttk.Label(control_frame, text="工作目录:").grid(row=0, column=0, sticky="w", padx=(0, 10))

        self.codex_file_var = tk.StringVar(value="")
        self.codex_file_entry = ttk.Entry(control_frame, textvariable=self.codex_file_var)
        self.codex_file_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))

        ttk.Button(control_frame, text="浏览", command=self._browse_codex_file).grid(row=0, column=2, padx=(0, 5))
        ttk.Button(control_frame, text="加载", command=self._load_codex_file).grid(row=0, column=3, padx=(0, 5))
        ttk.Button(control_frame, text="开始监控", command=self._start_codex_monitoring).grid(row=0, column=4, padx=(0, 5))
        ttk.Button(control_frame, text="停止监控", command=self._stop_codex_monitoring).grid(row=0, column=5, padx=(0, 5))
        ttk.Button(control_frame, text="清空", command=self._clear_codex_display).grid(row=0, column=6)

        # 刷新按钮（用于手动更新）
        self.refresh_button = ttk.Button(control_frame, text="刷新", command=self._manual_refresh)
        self.refresh_button.grid(row=0, column=7, padx=(5, 0))

        # 命令执行框
        exec_frame = ttk.LabelFrame(tab, text="Codex 命令执行", padding=10)
        exec_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        exec_frame.columnconfigure(1, weight=1)

        ttk.Label(exec_frame, text="指令:").grid(row=0, column=0, sticky="w", padx=(0, 10))

        self.codex_command_var = tk.StringVar(value="请根据README.md的要求完成任务")
        self.codex_command_entry = ttk.Entry(exec_frame, textvariable=self.codex_command_var)
        self.codex_command_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))

        self.codex_exec_button = ttk.Button(exec_frame, text="执行", command=self._execute_codex_command)
        self.codex_exec_button.grid(row=0, column=2, padx=(0, 5))

        self.codex_stop_button = ttk.Button(exec_frame, text="停止", command=self._stop_codex_execution, state="disabled")
        self.codex_stop_button.grid(row=0, column=3)

        # 显示完整命令（只读）
        ttk.Label(exec_frame, text="完整命令:", foreground="#666").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        self.codex_full_command_label = ttk.Label(exec_frame, text="codex exec --skip-git-repo-check --sandbox workspace-write --model gpt-5-codex-high \"...\"", foreground="#666")
        self.codex_full_command_label.grid(row=1, column=1, columnspan=3, sticky="w", pady=(5, 0))

        # 主显示区域 - 使用 PanedWindow 分隔
        paned = tk.PanedWindow(tab, orient=tk.HORIZONTAL, bg="#e0e0e0", sashwidth=4)
        paned.grid(row=2, column=0, sticky="nsew", pady=(0, 10))

        # 左侧：消息列表框架
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, width=300, minsize=200)

        ttk.Label(left_frame, text="消息列表", font=("Arial", 10, "bold")).pack(pady=(0, 5))

        # 消息列表框和滚动条
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill="both", expand=True)

        list_scrollbar = ttk.Scrollbar(list_frame)
        list_scrollbar.pack(side="right", fill="y")

        self.codex_message_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=list_scrollbar.set,
            font=("Monaco", 10),
            selectmode=tk.SINGLE,
            bg="#ffffff",
            fg="#000000",
            selectbackground="#e3f2fd",
            selectforeground="#0d47a1",
            activestyle="none"
        )
        self.codex_message_listbox.pack(side="left", fill="both", expand=True)
        self.codex_message_listbox.bind('<<ListboxSelect>>', lambda e: self._on_codex_message_select(e))
        list_scrollbar.config(command=self.codex_message_listbox.yview)

        # 右侧：消息详情框架
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, minsize=400)

        ttk.Label(right_frame, text="消息详情", font=("Arial", 10, "bold")).pack(pady=(0, 5))

        # 消息详情文本框
        detail_frame = ttk.Frame(right_frame)
        detail_frame.pack(fill="both", expand=True)

        self.codex_detail_text = scrolledtext.ScrolledText(
            detail_frame,
            wrap=tk.WORD,
            font=("Monaco", 11),
            bg="#ffffff",
            fg="#212529",
            insertbackground="#212529",
            padx=15,
            pady=10,
            relief="flat",
            borderwidth=1
        )
        self.codex_detail_text.pack(fill="both", expand=True)

        # 配置文本标签样式（类似 OpenAI 界面）
        self.codex_detail_text.tag_config("metadata", foreground="#6c757d", font=("Monaco", 10, "italic"))
        self.codex_detail_text.tag_config("user", foreground="#0066cc", font=("Monaco", 11, "bold"))
        self.codex_detail_text.tag_config("thinking", foreground="#7c4dff", font=("Monaco", 11, "italic"))
        self.codex_detail_text.tag_config("exec", foreground="#00695c", font=("Monaco", 10))
        self.codex_detail_text.tag_config("output", background="#f8f9fa", font=("Monaco", 10))
        self.codex_detail_text.tag_config("error", foreground="#d32f2f", font=("Monaco", 10, "bold"))
        self.codex_detail_text.tag_config("timestamp", foreground="#757575", font=("Monaco", 9))
        self.codex_detail_text.tag_config("codex", foreground="#ff6b35", font=("Monaco", 11, "bold"))
        self.codex_detail_text.tag_config("tokens", foreground="#9e9e9e", font=("Monaco", 9, "italic"))
        self.codex_detail_text.tag_config("status", foreground="#2196f3", font=("Monaco", 10, "bold"))
        self.codex_detail_text.tag_config("separator", foreground="#cccccc", font=("Monaco", 8))
        self.codex_detail_text.tag_config("highlight", background="#fffacd")

        # 底部状态栏
        status_frame = ttk.Frame(tab)
        status_frame.grid(row=3, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)

        self.codex_status_label = ttk.Label(status_frame, text="状态: 未加载文件", foreground="#666")
        self.codex_status_label.pack(side="left")

        # 自动跟踪复选框（移到状态栏中间位置）
        self.auto_follow_var = tk.BooleanVar(value=True)
        self.auto_follow_checkbox = ttk.Checkbutton(
            status_frame,
            text="自动跟踪最新",
            variable=self.auto_follow_var,
            command=self._on_auto_follow_change
        )
        self.auto_follow_checkbox.pack(side="left", padx=(20, 0))

        self.codex_line_count_label = ttk.Label(status_frame, text="消息数: 0", foreground="#666")
        self.codex_line_count_label.pack(side="right", padx=(0, 10))

        # 初始化变量
        self.codex_messages = []  # 存储解析后的消息
        self.codex_monitor_thread = None
        self.codex_monitoring = False
        self.codex_last_position = 0
        self.codex_file_mtime = 0
        self.codex_exec_proc = None  # Codex 执行进程
        self.codex_exec_thread = None  # Codex 执行线程
        self.codex_auto_follow = True  # 是否自动跟踪最新消息
        self.codex_is_executing = False  # 是否正在执行命令
        self.codex_message_positions = {}  # 消息在详情区的位置映射

    def _browse_codex_file(self):
        """浏览选择工作目录（包含 codex_output.txt）"""
        directory = filedialog.askdirectory(
            title="选择包含 codex_output.txt 的目录"
        )
        if directory:
            self.codex_file_var.set(directory)
            # 检查目录中是否有 codex_output.txt
            output_file = Path(directory) / "codex_output.txt"
            if output_file.exists():
                self._append_log(f"选择了目录: {directory} (包含 codex_output.txt)")
            else:
                self._append_log(f"选择了目录: {directory} (将创建新的 codex_output.txt)")

    def _load_codex_file(self):
        """加载并解析 codex_output.txt 文件"""
        dirpath = self.codex_file_var.get()
        if not dirpath:
            messagebox.showwarning("警告", "请先选择目录")
            return

        # 如果是目录，查找 codex_output.txt
        path = Path(dirpath)
        if path.is_dir():
            filepath = path / "codex_output.txt"
        else:
            # 如果是文件，直接使用
            filepath = path

        if not filepath.exists():
            # 文件不存在，创建空文件
            self._append_log(f"codex_output.txt 不存在，清空显示")
            self.codex_messages = []
            self._update_codex_display()
            self.codex_status_label.config(text=f"状态: 等待执行命令")
            return

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            self._parse_codex_content(content)
            self._update_codex_display()
            self.codex_status_label.config(text=f"状态: 已加载 {filepath.name}")
            self.codex_last_position = len(content)
            self.codex_file_mtime = filepath.stat().st_mtime
            self._append_log(f"成功加载 Codex 输出文件: {len(self.codex_messages)} 条消息")
        except Exception as e:
            messagebox.showerror("错误", f"加载文件失败: {e}")
            self._append_log(f"加载 Codex 文件失败: {e}")

    def _parse_codex_content(self, content: str):
        """解析 Codex 输出内容为结构化消息"""
        self.codex_messages = []
        lines = content.split('\n')

        current_message = None
        current_content = []
        in_thinking = False
        skip_next_codex = False  # 用于跳过thinking后面紧跟的重复codex内容

        for i, line in enumerate(lines):
            # 检测时间戳行 [2025-09-18T05:06:39]
            if line.startswith('[') and 'T' in line[:30] and ']' in line[:30]:
                # 保存上一个消息
                if current_message:
                    current_message['content'] = '\n'.join(current_content).strip()
                    # 过滤掉包含markdown标题格式的codex内容（这些实际上是thinking的内容）
                    if current_message['type'] == 'codex' and '**' in current_message['content']:
                        # 这是错误地标记为codex的thinking内容，跳过它
                        current_content = []
                        current_message = None
                    elif current_message['content'] or current_message['type'] == 'separator':
                        self.codex_messages.append(current_message)
                    current_content = []

                # 解析新消息
                try:
                    timestamp_end = line.index(']', 1)
                    timestamp = line[1:timestamp_end]
                    rest = line[timestamp_end+1:].strip()

                    # 判断消息类型
                    if 'OpenAI Codex' in rest:
                        current_message = {'type': 'header', 'timestamp': timestamp, 'title': 'Codex 初始化', 'content': rest}
                        in_thinking = False
                    elif 'User instructions:' in rest:
                        current_message = {'type': 'user', 'timestamp': timestamp, 'title': '用户指令'}
                        in_thinking = False
                    elif rest == 'thinking':
                        current_message = {'type': 'thinking', 'timestamp': timestamp, 'title': 'AI 思考'}
                        in_thinking = True
                        skip_next_codex = True  # thinking之后的codex可能是重复内容
                    elif rest == 'codex':
                        if skip_next_codex:
                            # 跳过thinking后面紧跟的codex（如果它包含markdown格式内容）
                            # 先收集内容，稍后判断
                            current_message = {'type': 'codex', 'timestamp': timestamp, 'title': 'Codex 输出', '_skip_if_markdown': True}
                            skip_next_codex = False
                        else:
                            current_message = {'type': 'codex', 'timestamp': timestamp, 'title': 'Codex 输出'}
                        in_thinking = False
                    elif rest.startswith('exec '):
                        command = rest[5:] if len(rest) > 5 else ''
                        current_message = {'type': 'exec', 'timestamp': timestamp, 'title': '执行命令', 'command': command}
                        in_thinking = False
                        skip_next_codex = False
                    elif 'succeeded' in rest:
                        current_message = {'type': 'success', 'timestamp': timestamp, 'title': '执行成功', 'content': rest}
                        in_thinking = False
                    elif 'failed' in rest or 'exited' in rest:
                        current_message = {'type': 'error', 'timestamp': timestamp, 'title': '执行失败', 'content': rest}
                        in_thinking = False
                    elif 'tokens used:' in rest:
                        current_message = {'type': 'tokens', 'timestamp': timestamp, 'title': 'Token 使用', 'content': rest}
                        in_thinking = False
                    else:
                        current_message = {'type': 'info', 'timestamp': timestamp, 'title': '信息', 'content': rest}
                except Exception:
                    # 如果解析失败，作为普通内容处理
                    if current_message:
                        current_content.append(line)
            elif line.startswith('--------'):
                # 分隔线
                if current_message:
                    current_message['content'] = '\n'.join(current_content).strip()
                    # 检查是否需要跳过包含markdown的codex
                    if current_message.get('_skip_if_markdown') and '**' in current_message['content']:
                        # 跳过这个错误的codex
                        pass
                    elif current_message['content'] or current_message['type'] == 'separator':
                        # 移除临时标记
                        if '_skip_if_markdown' in current_message:
                            del current_message['_skip_if_markdown']
                        self.codex_messages.append(current_message)
                    current_content = []
                    current_message = None
                # 添加分隔线作为特殊消息
                self.codex_messages.append({'type': 'separator', 'timestamp': '', 'title': '---', 'content': ''})
                in_thinking = False
                skip_next_codex = False
            elif current_message:
                # 添加到当前消息内容
                current_content.append(line)
            elif not current_message and line.strip() and i < 20:
                # 处理开头的元数据
                if not self.codex_messages or self.codex_messages[-1]['type'] != 'metadata':
                    self.codex_messages.append({
                        'type': 'metadata',
                        'timestamp': '',
                        'title': '元数据',
                        'content': line
                    })
                else:
                    self.codex_messages[-1]['content'] += '\n' + line

        # 保存最后一个消息
        if current_message:
            current_message['content'] = '\n'.join(current_content).strip()
            # 检查是否需要跳过包含markdown的codex
            if current_message.get('_skip_if_markdown') and '**' in current_message['content']:
                # 跳过这个错误的codex
                pass
            elif current_message['content'] or current_message['type'] == 'separator':
                # 移除临时标记
                if '_skip_if_markdown' in current_message:
                    del current_message['_skip_if_markdown']
                self.codex_messages.append(current_message)

    def _update_codex_display(self):
        """更新消息列表显示"""
        self.codex_message_listbox.delete(0, tk.END)

        for i, msg in enumerate(self.codex_messages):
            # 格式化列表项显示
            # 从完整时间戳中提取时间部分 (HH:MM:SS)
            if 'T' in msg['timestamp'] and len(msg['timestamp']) > 11:
                # 格式：2025-09-18T16:24:10 -> 16:24:10
                timestamp = msg['timestamp'][11:19] if len(msg['timestamp']) >= 19 else msg['timestamp']
            else:
                timestamp = msg['timestamp'][:8] if len(msg['timestamp']) > 8 else msg['timestamp']
            title = msg['title']

            # 根据类型添加图标
            icon = ''
            if msg['type'] == 'user':
                icon = '👤'
            elif msg['type'] == 'thinking':
                icon = '🤔'
            elif msg['type'] == 'exec':
                icon = '⚡'
            elif msg['type'] == 'success':
                icon = '✅'
            elif msg['type'] == 'error':
                icon = '❌'
            elif msg['type'] == 'codex':
                icon = '🤖'
            elif msg['type'] == 'tokens':
                icon = '🎫'
            elif msg['type'] == 'metadata':
                icon = 'ℹ️'
            elif msg['type'] == 'header':
                icon = '📋'
            elif msg['type'] == 'separator':
                icon = '━'

            # 组合显示文本
            if timestamp:
                display_text = f"{icon} [{timestamp}] {title}"
            else:
                display_text = f"{icon} {title}"

            # 对于命令，显示部分命令内容
            if msg['type'] == 'exec' and 'command' in msg:
                cmd_preview = msg['command'][:40] + '...' if len(msg['command']) > 40 else msg['command']
                display_text = f"{icon} [{timestamp}] {title}: {cmd_preview}"

            self.codex_message_listbox.insert(tk.END, display_text)

            # 根据类型设置颜色
            if msg['type'] == 'error':
                self.codex_message_listbox.itemconfig(i, {'fg': '#d32f2f'})
            elif msg['type'] == 'success':
                self.codex_message_listbox.itemconfig(i, {'fg': '#388e3c'})
            elif msg['type'] == 'thinking':
                self.codex_message_listbox.itemconfig(i, {'fg': '#7c4dff'})
            elif msg['type'] == 'exec':
                self.codex_message_listbox.itemconfig(i, {'fg': '#00695c'})
            elif msg['type'] == 'codex':
                self.codex_message_listbox.itemconfig(i, {'fg': '#ff6b35'})
            elif msg['type'] == 'separator':
                self.codex_message_listbox.itemconfig(i, {'fg': '#cccccc'})

        self.codex_line_count_label.config(text=f"消息数: {len(self.codex_messages)}")

        # 同时更新详情视图
        self._populate_detail_view()

    def _on_auto_follow_change(self):
        """切换自动跟踪模式"""
        self.codex_auto_follow = self.auto_follow_var.get()
        if self.codex_auto_follow and self.codex_messages:
            # 如果启用自动跟踪，立即刷新显示并跳到最后
            self._refresh_codex_display()
            self.codex_message_listbox.see(tk.END)
            self.codex_message_listbox.selection_clear(0, tk.END)
            self.codex_message_listbox.selection_set(tk.END)
            # 使用None作为event参数，表示这不是用户直接点击
            self._on_codex_message_select(None)
            self._append_log("[UI] 自动跟踪已启用")
        else:
            self._append_log("[UI] 自动跟踪已禁用，显示已冻结。点击'刷新'按钮手动更新")

    def _refresh_codex_display(self):
        """手动刷新显示（用于非自动跟踪模式）"""
        # 保存当前选择
        current_selection = self.codex_message_listbox.curselection()
        selected_index = current_selection[0] if current_selection else None

        # 更新显示
        self._update_codex_display()

        # 恢复选择（如果之前有选择）
        if selected_index is not None and selected_index < len(self.codex_messages):
            self.codex_message_listbox.selection_set(selected_index)
            # 触发选择事件来更新详情视图
            self._on_codex_message_select(None)

        # 更新计数
        self.codex_line_count_label.config(text=f"消息数: {len(self.codex_messages)}")

    def _on_codex_message_select(self, event):
        """当选择消息时滚动到对应位置"""
        selection = self.codex_message_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        total = self.codex_message_listbox.size()

        # 用户手动选择时的逻辑
        if event:  # 只有真实的用户事件才改变自动跟踪状态
            # 如果正在执行或监控中
            if self.codex_is_executing or self.codex_monitoring:
                if index < total - 1:
                    # 用户选择了历史消息，立即禁用自动跟踪
                    if self.codex_auto_follow:
                        self.auto_follow_var.set(False)
                        self.codex_auto_follow = False
                        # 显示提示（可选）
                        self._append_log("[UI] 已暂停自动跟踪，正在查看历史消息")
                elif index == total - 1:
                    # 用户选择了最新消息，可以重新启用自动跟踪
                    if not self.codex_auto_follow:
                        self.auto_follow_var.set(True)
                        self.codex_auto_follow = True
                        self._append_log("[UI] 已恢复自动跟踪最新消息")

        if index >= len(self.codex_messages):
            return

        # 滚动到对应消息的位置
        if index in self.codex_message_positions:
            start_line, _ = self.codex_message_positions[index]
            # 滚动到该消息的开始位置
            self.codex_detail_text.see(f"{start_line}.0")
            # 高亮当前选中的消息段
            self._highlight_selected_message(index)

    def _format_thinking_content(self, content: str) -> str:
        """格式化思考内容，使其更易读"""
        # 为标题添加换行
        lines = content.split('\n')
        formatted = []
        for line in lines:
            # 检测是否为标题（以**开头和结尾）
            if line.strip().startswith('**') and line.strip().endswith('**'):
                formatted.append('\n' + line + '\n')
            else:
                formatted.append(line)
        return '\n'.join(formatted)

    def _populate_detail_view(self):
        """填充详情视图，所有消息连续显示"""
        self.codex_detail_text.delete(1.0, tk.END)
        self.codex_message_positions.clear()

        current_line = 1

        for i, msg in enumerate(self.codex_messages):
            start_line = current_line

            # 添加分隔符（除了第一条消息）
            if i > 0:
                self.codex_detail_text.insert(tk.END, "\n" + "═" * 80 + "\n\n", "separator")
                current_line += 3
                start_line = current_line

            # 显示时间戳和标题
            if msg['timestamp']:
                self.codex_detail_text.insert(tk.END, f"[{msg['timestamp']}] ", "timestamp")

            # 根据消息类型获取标签
            tag_for_type = {
                'user': 'user',
                'thinking': 'thinking',
                'exec': 'exec',
                'codex': 'codex',
                'tokens': 'tokens',
                'error': 'error',
                'success': 'exec',
                'status': 'status',
                'metadata': 'metadata'
            }.get(msg['type'], '')

            # 显示标题
            self.codex_detail_text.insert(tk.END, f"{msg['title']}\n", tag_for_type if tag_for_type else None)
            current_line += 1

            # 显示命令（如果有）
            if 'command' in msg and msg['command']:
                self.codex_detail_text.insert(tk.END, f"命令: {msg['command']}\n", "exec")
                current_line += 1

            # 显示内容
            content = msg.get('content', '')
            if content and msg['type'] != 'separator':
                self.codex_detail_text.insert(tk.END, "\n", None)
                current_line += 1

                # 对不同类型的内容应用不同的标签
                content_tag = "output" if msg['type'] in ['exec', 'success'] else \
                             "error" if msg['type'] == 'error' else \
                             "thinking" if msg['type'] == 'thinking' else None

                # 格式化thinking内容
                if msg['type'] == 'thinking':
                    content = self._format_thinking_content(content)

                self.codex_detail_text.insert(tk.END, content, content_tag)
                # 计算内容的行数
                content_lines = content.count('\n') + 1
                current_line += content_lines

            # 记录消息位置
            end_line = current_line - 1
            self.codex_message_positions[i] = (start_line, end_line)

        # 添加结束标记
        if self.codex_messages:
            self.codex_detail_text.insert(tk.END, "\n" + "═" * 80 + "\n", "separator")

    def _highlight_selected_message(self, index):
        """高亮显示选中的消息"""
        # 先清除所有高亮
        self.codex_detail_text.tag_remove("highlight", "1.0", tk.END)

        # 高亮选中的消息
        if index in self.codex_message_positions:
            start_line, end_line = self.codex_message_positions[index]
            self.codex_detail_text.tag_add("highlight", f"{start_line}.0", f"{end_line}.end+1c")

            # 配置高亮样式
            self.codex_detail_text.tag_config("highlight", background="#fffacd")
            self.codex_detail_text.tag_raise("highlight")

    def _execute_codex_command(self):
        """执行 Codex 命令"""
        dirpath = self.codex_file_var.get()
        if not dirpath:
            messagebox.showwarning("警告", "请先选择工作目录")
            return

        command = self.codex_command_var.get().strip()
        if not command:
            messagebox.showwarning("警告", "请输入要执行的指令")
            return

        # 构建完整命令
        full_command = f'codex exec --skip-git-repo-check --sandbox workspace-write --model gpt-5-codex-high "{command}"'
        self.codex_full_command_label.config(text=full_command[:100] + "..." if len(full_command) > 100 else full_command)

        # 禁用执行按钮，启用停止按钮
        self.codex_exec_button.config(state="disabled")
        self.codex_stop_button.config(state="normal")

        # 设置执行状态
        self.codex_is_executing = True

        # 启用自动跟踪
        self.auto_follow_var.set(True)
        self.codex_auto_follow = True

        # 设置工作目录
        work_dir = Path(dirpath)
        if not work_dir.is_dir():
            work_dir = work_dir.parent

        # 启动监控（如果还没有）
        output_file = work_dir / "codex_output.txt"
        if not self.codex_monitoring:
            self._start_codex_monitoring()

        # 在线程中执行命令
        self.codex_exec_thread = threading.Thread(
            target=self._run_codex_command,
            args=(full_command, work_dir),
            daemon=True
        )
        self.codex_exec_thread.start()

        self.codex_status_label.config(text="状态: 正在执行 Codex 命令...")
        self._append_log(f"开始执行 Codex 命令: {command[:50]}...")

    def _run_codex_command(self, command, work_dir):
        """在后台线程中运行 Codex 命令"""
        try:
            # 获取 API key
            api_key = self.api_key_var.get().strip()
            env = os.environ.copy()
            if api_key:
                env["CODEX_API_KEY"] = api_key
            else:
                # 尝试从环境变量获取
                if "CODEX_API_KEY" not in env:
                    # 尝试从文件读取
                    try:
                        key_file = Path(".cache/codex_api_key")
                        if key_file.exists():
                            api_key = key_file.read_text(encoding="utf-8").strip()
                            if api_key:
                                env["CODEX_API_KEY"] = api_key
                    except:
                        pass

            # 确保 codex_output.txt 存在
            output_file = work_dir / "codex_output.txt"
            error_file = work_dir / "codex_error.txt"
            status_file = work_dir / "codex_status.txt"

            # 处理文件：
            # - output_file: 追加模式，不覆盖
            # - error_file 和 status_file: 覆盖模式
            if not output_file.exists():
                output_file.write_text("", encoding="utf-8")
            error_file.write_text("", encoding="utf-8")
            status_file.write_text("running", encoding="utf-8")

            # 构建命令数组（不使用 shell=True）
            cmd_parts = [
                "codex",
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "workspace-write",
                "--model",
                "gpt-5-codex-high",
                self.codex_command_var.get().strip()
            ]

            self._append_log(f"执行命令: codex exec 在目录 {work_dir}")

            # 执行命令，实现流式输出
            self.codex_exec_proc = subprocess.Popen(
                cmd_parts,
                cwd=str(work_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,  # 行缓冲
                env=env
            )

            # 启动线程读取输出
            import threading

            def stream_output():
                """流式读取并追加输出"""
                try:
                    while True:
                        line = self.codex_exec_proc.stdout.readline()
                        if not line:
                            break
                        # 追加到文件（不覆盖）
                        with open(output_file, "a", encoding="utf-8") as f:
                            f.write(line)
                            f.flush()
                except:
                    pass

            def stream_error():
                """流式读取错误输出"""
                try:
                    while True:
                        line = self.codex_exec_proc.stderr.readline()
                        if not line:
                            break
                        # 追加到错误文件
                        with open(error_file, "a", encoding="utf-8") as f:
                            f.write(line)
                            f.flush()
                except:
                    pass

            # 启动输出线程
            out_thread = threading.Thread(target=stream_output, daemon=True)
            err_thread = threading.Thread(target=stream_error, daemon=True)
            out_thread.start()
            err_thread.start()

            # 等待命令完成
            return_code = self.codex_exec_proc.wait()
            out_thread.join(timeout=1)
            err_thread.join(timeout=1)

            # 写入状态
            status_file.write_text(str(return_code), encoding="utf-8")

            # 在主线程中更新状态
            self.root.after(0, lambda: self._on_codex_command_complete(return_code))

        except FileNotFoundError:
            self.root.after(0, lambda: self._on_codex_command_error("找不到 codex 命令，请确保已安装 Codex"))
        except Exception as e:
            self.root.after(0, lambda: self._on_codex_command_error(str(e)))

    def _play_notification_sound(self, success=True):
        """播放提示音（使用系统声音）"""
        try:
            import platform
            system = platform.system()

            if system == "Darwin":  # macOS
                # 使用 macOS 系统声音
                if success:
                    # 成功提示音 (Glass)
                    os.system("afplay /System/Library/Sounds/Glass.aiff 2>/dev/null &")
                else:
                    # 错误提示音 (Basso)
                    os.system("afplay /System/Library/Sounds/Basso.aiff 2>/dev/null &")
            elif system == "Windows":
                import winsound
                if success:
                    winsound.MessageBeep(winsound.MB_OK)
                else:
                    winsound.MessageBeep(winsound.MB_ICONHAND)
            else:  # Linux
                # 尝试使用系统铃声
                print('\a')  # ASCII bell
        except Exception:
            # 如果无法播放声音，静默失败
            pass

    def _on_codex_command_complete(self, return_code):
        """命令执行完成的回调"""
        # 重新启用执行按钮，禁用停止按钮
        self.codex_exec_button.config(state="normal")
        self.codex_stop_button.config(state="disabled")

        # 清除执行状态
        self.codex_is_executing = False

        # 根据返回码显示不同的状态和播放不同的声音
        if return_code == 0:
            self._append_log("Codex 命令执行成功")
            self.codex_status_label.config(text="状态: ✅ 执行成功")
            self._play_notification_sound(success=True)  # 播放成功提示音
        elif return_code == 124:
            self._append_log("Codex 执行超时")
            self.codex_status_label.config(text="状态: ⏱️ 执行超时")
            self._play_notification_sound(success=False)  # 播放错误提示音
        elif return_code == 127:
            self._append_log("找不到 codex 命令")
            self.codex_status_label.config(text="状态: ❌ 找不到命令")
            self._play_notification_sound(success=False)  # 播放错误提示音
        else:
            self._append_log(f"Codex 执行完成，返回码: {return_code}")
            self.codex_status_label.config(text=f"状态: ⚠️ 退出码 {return_code}")
            self._play_notification_sound(success=False)  # 播放错误提示音

        # 重新加载文件以显示最终内容（包括错误和状态）
        self._load_codex_file()

        # 执行完成后仍保持自动跟踪，显示最后的结果
        if self.codex_auto_follow and self.codex_messages:
            self.codex_message_listbox.see(tk.END)
            self.codex_message_listbox.selection_clear(0, tk.END)
            self.codex_message_listbox.selection_set(tk.END)
            self.codex_message_listbox.event_generate('<<ListboxSelect>>')

    def _on_codex_command_error(self, error_msg):
        """命令执行错误的回调"""
        self.codex_exec_button.config(state="normal")
        self.codex_stop_button.config(state="disabled")
        self._append_log(f"执行 Codex 命令失败: {error_msg}")
        self.codex_status_label.config(text="状态: 执行失败")
        messagebox.showerror("错误", f"执行命令失败: {error_msg}")

    def _stop_codex_execution(self):
        """停止 Codex 命令执行"""
        if self.codex_exec_proc and self.codex_exec_proc.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(os.getpgid(self.codex_exec_proc.pid), signal.SIGTERM)
                else:
                    self.codex_exec_proc.terminate()
                self._append_log("已停止 Codex 命令执行")
            except Exception as e:
                self._append_log(f"停止命令失败: {e}")

        self.codex_exec_button.config(state="normal")
        self.codex_stop_button.config(state="disabled")
        self.codex_status_label.config(text="状态: 已停止")
        self.codex_is_executing = False

    def _start_codex_monitoring(self):
        """开始监控文件变化"""
        dirpath = self.codex_file_var.get()
        if not dirpath:
            messagebox.showwarning("警告", "请先选择工作目录")
            return

        # 确定 codex_output.txt 的路径
        path = Path(dirpath)
        if path.is_dir():
            filepath = path / "codex_output.txt"
        else:
            filepath = path
            path = path.parent

        # 如果文件不存在，创建空文件
        if not filepath.exists():
            filepath.touch()
            self._append_log(f"创建了 {filepath.name}")

        if self.codex_monitoring:
            return  # 已在监控中

        self.codex_monitoring = True
        self.codex_monitor_thread = threading.Thread(
            target=self._monitor_codex_file,
            args=(str(filepath),),
            daemon=True
        )
        self.codex_monitor_thread.start()
        self.codex_status_label.config(text=f"状态: 监控中 - {filepath.name}")
        self._append_log(f"开始监控 Codex 文件: {filepath}")

    def _monitor_codex_file(self, filepath):
        """监控文件变化的线程函数"""
        import time
        path = Path(filepath)

        # 确定工作目录
        if path.is_dir():
            work_dir = path
            output_file = path / "codex_output.txt"
        else:
            work_dir = path.parent
            output_file = path

        while self.codex_monitoring:
            try:
                if output_file.exists():
                    current_mtime = output_file.stat().st_mtime

                    # 检查文件是否被修改
                    if current_mtime > self.codex_file_mtime:
                        with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()

                        # 在主线程中更新 UI
                        self.root.after(0, lambda: self._update_codex_from_monitor_full(content, work_dir))
                        self.codex_file_mtime = current_mtime
                        self.codex_last_position = len(content)

                # 同时检查 status 和 error 文件
                self._check_status_and_error_files(work_dir)

            except Exception as e:
                print(f"监控文件出错: {e}")

            # 每秒检查一次
            time.sleep(1)

    def _check_status_and_error_files(self, work_dir):
        """检查状态和错误文件"""
        try:
            status_file = work_dir / "codex_status.txt"
            error_file = work_dir / "codex_error.txt"

            # 检查状态文件
            if status_file.exists():
                status = status_file.read_text(encoding="utf-8").strip()
                if status:
                    if status == "running":
                        status_text = "🔄 运行中..."
                    elif status == "0":
                        status_text = "✅ 执行成功"
                    else:
                        status_text = f"⚠️ 退出码 {status}"

                    # 在主线程更新状态
                    self.root.after(0, lambda: self._update_status_display(status_text))

            # 检查错误文件
            if error_file.exists():
                error_content = error_file.read_text(encoding="utf-8").strip()
                if error_content:
                    # 检查是否需要添加错误消息
                    attr_name = 'codex_last_error'
                    if not hasattr(self, attr_name) or getattr(self, attr_name) != error_content:
                        setattr(self, attr_name, error_content)
                        # 在主线程添加错误消息
                        self.root.after(0, lambda: self._add_error_message(error_content))
        except:
            pass

    def _update_codex_from_monitor_full(self, content, work_dir):
        """从监控线程更新显示（带状态检查）"""
        # 调用原有的更新方法
        self._update_codex_from_monitor(content)

    def _add_error_message(self, error_content):
        """添加错误消息到列表"""
        # 避免重复添加相同的错误
        if not any(msg['type'] == 'error' and error_content[:50] in msg.get('content', '')[:50] for msg in self.codex_messages[-3:] if msg):
            self.codex_messages.append({
                'type': 'error',
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'title': '❌ 错误输出',
                'content': error_content
            })
            self._update_codex_display()

            # 如果正在执行，自动跳转到错误
            if self.codex_is_executing or self.codex_auto_follow:
                self.codex_message_listbox.see(tk.END)
                self.codex_message_listbox.selection_clear(0, tk.END)
                self.codex_message_listbox.selection_set(tk.END)
                self.codex_message_listbox.event_generate('<<ListboxSelect>>')

    def _update_status_display(self, status_text):
        """更新状态显示"""
        self.codex_status_label.config(text=f"状态: {status_text}")

    def _update_codex_from_monitor(self, content):
        """从监控线程更新显示"""
        # 解析新内容（总是解析，但不一定显示）
        self._parse_codex_content(content)

        # 如果没有启用自动跟踪，不更新显示
        if not self.codex_auto_follow:
            # 只在内部更新消息列表，但不刷新UI
            # 可以在状态栏显示有新消息的提示
            new_count = len(self.codex_messages)
            try:
                # 更新消息计数标签（轻量级提示）
                self.codex_line_count_label.config(text=f"消息数: {new_count} (有新消息)")
            except:
                pass
            return  # 直接返回，不更新显示

        # 自动跟踪模式：正常更新显示
        prev_message_count = len(self.codex_messages) - 1  # 因为已经解析了
        has_new_messages = True  # 有新内容才会调用这个函数

        # 更新列表显示
        self._update_codex_display()

        # 自动选中并显示最后一条消息
        if has_new_messages:
            self.codex_message_listbox.see(tk.END)
            self.codex_message_listbox.selection_clear(0, tk.END)
            self.codex_message_listbox.selection_set(tk.END)
            # 直接调用而不是触发事件
            self._on_codex_message_select(None)
            # 详情区滚动到底部
            self.codex_detail_text.see(tk.END)

    def _stop_codex_monitoring(self):
        """停止监控"""
        if not self.codex_monitoring:
            messagebox.showinfo("信息", "未在监控中")
            return

        self.codex_monitoring = False
        if self.codex_monitor_thread:
            self.codex_monitor_thread.join(timeout=2)
        self.codex_status_label.config(text="状态: 监控已停止")
        self._append_log("停止监控 Codex 文件")

    def _manual_refresh(self):
        """手动刷新显示（点击刷新按钮）"""
        if not self.codex_auto_follow:
            # 在非自动跟踪模式下手动刷新
            self._refresh_codex_display()
            self._append_log("[UI] 手动刷新完成")
            # 更新提示
            if "有新消息" in self.codex_line_count_label.cget("text"):
                self.codex_line_count_label.config(text=f"消息数: {len(self.codex_messages)}")
        else:
            # 自动跟踪模式下，刷新按钮只是确保跳到最新
            self.codex_message_listbox.see(tk.END)
            self.codex_message_listbox.selection_clear(0, tk.END)
            self.codex_message_listbox.selection_set(tk.END)
            self._on_codex_message_select(None)

    def _clear_codex_display(self):
        """清空显示"""
        self.codex_messages = []
        self.codex_message_listbox.delete(0, tk.END)
        self.codex_detail_text.delete(1.0, tk.END)
        self.codex_line_count_label.config(text="消息数: 0")
        self.codex_last_position = 0
        self.codex_file_mtime = 0
        self.codex_status_label.config(text="状态: 已清空")
        self._append_log("清空 Codex 显示")

    # ---------------- ghostty operations ----------------
    def _ghostty_embed_help(self):
        msg = (
            "构建步骤（macOS）：\n\n"
            "1) 安装 Zig 0.14+（例如: brew install zig）。\n"
            "2) 在仓库 ghostty/ 目录执行：\n"
            "   优先（Metal）：\n"
            "   zig build -Dapp-runtime=none -Doptimize=ReleaseSafe -Demit-shared-lib=true\n"
            "   若 Metal 出现崩溃（常见于动态子类注册失败），请用 OpenGL 方案：\n"
            "   zig build -Dapp-runtime=none -Drenderer=opengl -Doptimize=ReleaseSafe -Demit-shared-lib=true\n"
            "   成功后将在 ghostty/zig-out/lib/ 生成 libghostty.dylib。\n"
            "3) 若路径不同，可在环境变量 LIBGHOSTTY_PATH 指定 dylib 完整路径。\n\n"
            "完成后，回到本页点击“嵌入到下方区域”。"
        )
        messagebox.showinfo("libghostty 构建指引", msg)

    def _ghostty_embed_start(self):
        if _plat.system() != 'Darwin':
            messagebox.showwarning("不支持的平台", "内嵌 Ghostty 仅支持 macOS。")
            return
        if GhosttyEmbedder is None:
            messagebox.showwarning("模块缺失", "未找到 tools/ghostty_embed.py 或依赖加载失败。")
            return
        try:
            if self._ghostty_embedder is None:
                self._ghostty_embedder = GhosttyEmbedder(self.root)
            cont = self.ghostty_embed_container
            try:
                # Ensure the NSView is realized so winfo_id returns a real pointer
                cont.update_idletasks()
                self.root.update_idletasks()
            except Exception:
                pass
            self._ghostty_embedder.embed_into_tk(cont, working_dir=self.sboxes_root_var.get() or os.getcwd())
            try:
                cont.focus_set()
            except Exception:
                pass
            self._append_log("已在 GhosttyAI 标签内嵌入 Ghostty 视图（试验特性）")
        except Exception as e:
            messagebox.showerror("嵌入失败", str(e))

    def _ghostty_embed_stop(self):
        try:
            if self._ghostty_embedder is not None:
                self._ghostty_embedder.free()
                self._append_log("已释放内嵌 Ghostty 资源")
        except Exception:
            pass

    def _on_ghostty_container_resize(self, event):
        try:
            if self._ghostty_embedder is not None:
                self._ghostty_embedder.update_size(event.width, event.height)
                # Update scale if changed
                scale = self._ghostty_embedder.suggest_scale(self.ghostty_embed_container)
                self._ghostty_embedder.update_scale(scale)
                # Reposition host NSView overlay (PyObjC path)
                if hasattr(self._ghostty_embedder, '_place_nsview_over_tk'):
                    self._ghostty_embedder._place_nsview_over_tk(self.ghostty_embed_container)
        except Exception:
            pass

    def _on_ghostty_embed_key(self, event):
        try:
            if self._ghostty_embedder is not None and getattr(event, 'char', ''):
                self._ghostty_embedder.send_text(event.char)
        except Exception:
            pass

    # ---------------- Ghostty integration ----------------
    def _ghostty_check(self):
        try:
            in_path = shutil.which("ghostty") is not None
        except Exception:
            in_path = False
        app_paths = [
            Path("/Applications/Ghostty.app"),
            Path.home() / "Applications/Ghostty.app",
        ]
        app_found = any(p.exists() for p in app_paths)
        msg = [
            f"ghostty 命令: {'可用' if in_path else '不可用'}",
            f"Ghostty.app: {'已安装' if app_found else '未发现'}",
        ]
        messagebox.showinfo("Ghostty 检测", "\n".join(msg))

    def _ghostty_launch_default(self):
        # Try to launch Ghostty as an external window (best-effort)
        if shutil.which("ghostty"):
            try:
                subprocess.Popen(["ghostty"], start_new_session=True)
                self._append_log("已尝试启动 ghostty (PATH)")
                return
            except Exception as e:
                self._append_log(f"启动 ghostty 失败: {e}")
        # macOS app
        try:
            subprocess.Popen(["open", "-a", "Ghostty"])
            self._append_log("已尝试通过 macOS 打开 Ghostty.app")
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动 Ghostty: {e}")

    def _ghostty_launch_at(self, path: Path):
        try:
            cwd = str(path.resolve())
        except Exception:
            cwd = str(path)
        # Prefer CLI if present to set CWD for the launched process
        if shutil.which("ghostty"):
            try:
                subprocess.Popen(["ghostty"], cwd=cwd, start_new_session=True)
                self._append_log(f"已在 {cwd} 尝试启动 ghostty")
                return
            except Exception as e:
                self._append_log(f"启动 ghostty 失败: {e}")
        # Fall back to macOS app (cwd may not propagate to shell inside)
        try:
            subprocess.Popen(["open", "-a", "Ghostty"], cwd=cwd)
            self._append_log(f"已尝试通过 macOS 在 {cwd} 打开 Ghostty.app")
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动 Ghostty: {e}")

    # ---- Simple built-in terminal (PTY-based, non-Ghostty) ----
    def _ghostty_simple_start(self):
        if self._ghostty_alive:
            return
        shell = os.environ.get("SHELL") or "/bin/zsh"
        try:
            pid, master = pty.fork()
            if pid == 0:
                # Child: exec shell
                try:
                    os.execvp(shell, [shell, "-l"])
                except Exception:
                    os._exit(1)
            else:
                # Parent
                self._ghostty_pty_master = master
                self._ghostty_pty_pid = pid
                self._ghostty_alive = True
                self.ghostty_text.insert(tk.END, f"[启动 {shell} -l]\n")
                self.ghostty_text.see(tk.END)
                self._ghostty_reader = threading.Thread(target=self._ghostty_simple_reader, daemon=True)
                self._ghostty_reader.start()
        except Exception as e:
            messagebox.showerror("启动失败", str(e))

    def _ghostty_simple_reader(self):
        try:
            while self._ghostty_alive and self._ghostty_pty_master is not None:
                r, _, _ = select.select([self._ghostty_pty_master], [], [], 0.2)
                if not r:
                    continue
                try:
                    data = os.read(self._ghostty_pty_master, 4096)
                    if not data:
                        break
                    self.ui_queue.put(("ghostty_out", data.decode(errors="replace")))
                except OSError:
                    break
        finally:
            self._ghostty_alive = False
            try:
                if self._ghostty_pty_master is not None:
                    os.close(self._ghostty_pty_master)
            except Exception:
                pass
            self._ghostty_pty_master = None
            self._ghostty_pty_pid = None

    def _ghostty_simple_send(self, text: str):
        if not self._ghostty_alive or self._ghostty_pty_master is None:
            self._ghostty_simple_start()
        try:
            os.write(self._ghostty_pty_master, (text + "\n").encode())
            self.ghostty_input.delete(0, tk.END)
        except Exception as e:
            messagebox.showerror("发送失败", str(e))

    def _ghostty_simple_stop(self):
        if not self._ghostty_alive:
            return
        try:
            # Politely ask shell to exit
            os.write(self._ghostty_pty_master, b"exit\n")
        except Exception:
            pass
        self._ghostty_alive = False

    # ---------------- stats refresh (removed chain total feature) ----------------

    # ---------------- backup/cleanup ----------------
    def _backup_current_history_threaded(self):
        threading.Thread(target=self._backup_current_history, daemon=True).start()

    def _backup_current_history(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("确认", "当前有任务在执行，确定要备份并移动历史目录吗？这可能影响正在执行的步骤。"):
                return
        try:
            artifacts = Path(self.artifacts_root_var.get()).resolve()
            timeline = Path(self.sboxes_root_var.get()).resolve()
            to_backup = [p for p in [artifacts, timeline] if p.exists()]

            if not to_backup:
                self._append_log("未发现可备份的目录（.artifacts 或 .sboxes）。")
                messagebox.showinfo("无可备份内容", "未发现 .artifacts 或 .sboxes。")
                return

            target_root = Path("temp").resolve()
            target_root.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            bak_dir = target_root / f"{stamp}-bak"
            idx = 1
            while bak_dir.exists():
                idx += 1
                bak_dir = target_root / f"{stamp}-bak-{idx}"
            bak_dir.mkdir(parents=True, exist_ok=True)

            import shutil
            self._append_log(f"开始备份到: {bak_dir}")
            for p in to_backup:
                dest = bak_dir / p.name
                try:
                    shutil.move(str(p), str(dest))
                    self._append_log(f"已移动 {p} → {dest}")
                except Exception as e:
                    self._append_log(f"移动失败 {p}: {e}")
                    messagebox.showerror("移动失败", f"{p}: {e}")
                    return

            self._append_log("备份完成。")
            messagebox.showinfo("完成", f"已备份到 {bak_dir}")
        except Exception as e:
            self._append_log(f"备份过程出错: {e}")
            messagebox.showerror("错误", str(e))

    # ---------------- style management ----------------
    def _styles_dir(self) -> Path:
        p = Path(".cache/styles")
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _project_styles_dir(self) -> Path:
        return Path("styles")

    def _style_file_path(self, name: str) -> Optional[Path]:
        if not name:
            return None
        # prefer local cache override, then project styles
        cache_fp = self._styles_dir() / f"{self._sanitize_style_name(name)}.md"
        if cache_fp.exists():
            return cache_fp
        proj_dir = self._project_styles_dir()
        proj_fp = proj_dir / f"{self._sanitize_style_name(name)}.md"
        if proj_fp.exists():
            return proj_fp
        return cache_fp  # return cache path as destination for save

    def _available_styles(self) -> list[str]:
        names = set(["timeline"])  # default
        try:
            for fp in self._styles_dir().glob("*.md"):
                names.add(fp.stem)
        except Exception:
            pass
        try:
            pdir = self._project_styles_dir()
            if pdir.exists():
                for fp in pdir.glob("*.md"):
                    names.add(fp.stem)
        except Exception:
            pass
        return sorted(names)

    def _refresh_styles(self):
        values = self._available_styles()
        try:
            self.style_combo["values"] = values
        except Exception:
            pass
        try:
            self.style_combo_readme["values"] = values
        except Exception:
            pass
        # keep existing selection if present; else default to timeline
        cur = self.style_var.get()
        if cur not in values:
            self.style_var.set("timeline")
        # recalc output root (if not overridden)
        self._apply_style_to_out_path()

    def _sanitize_style_name(self, name: str) -> str:
        s = name.strip().lower()
        return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in s) or "timeline"

    def _on_style_change(self):
        # propagate style change to out path and template editor
        self._apply_style_to_out_path()
        # load template content for this style if exists
        try:
            fp = self._style_file_path(self.style_var.get())
            if fp and fp.exists():
                self._set_editor_text(self.readme_template_editor, fp.read_text(encoding="utf-8"))
            else:
                # fallback to built-in default
                self._set_editor_text(self.readme_template_editor, self._default_readme_template())
        except Exception:
            pass

    def _apply_style_to_out_path(self):
        try:
            new_default = str((Path(".sboxes")).resolve())
        except Exception:
            new_default = str(Path(".sboxes").resolve())
        cur = str(Path(self.sboxes_root_var.get()).resolve()) if self.sboxes_root_var.get() else ""
        # Update if user hasn't overridden or if current equals last derived
        if not self._out_overridden or cur == self._last_derived_out or cur == "":
            try:
                # set without marking overridden
                self.sboxes_root_var.set(str(Path(new_default)))
                self._last_derived_out = new_default
                self._out_overridden = False
            except Exception:
                pass

    def _edit_current_style(self):
        # focus template tab and load current style file
        try:
            fp = self._style_file_path(self.style_var.get())
            if fp and fp.exists():
                self._set_editor_text(self.readme_template_editor, fp.read_text(encoding="utf-8"))
            else:
                self._set_editor_text(self.readme_template_editor, self._default_readme_template())
            # best-effort: switch to template tab if present
            # find notebook widget by traversal
            # Not strictly necessary; user can click tab manually
        except Exception:
            pass

    def _import_style_file(self):
        fp = filedialog.askopenfilename(title="导入风格模板 (.md)", filetypes=[("Markdown", "*.md"), ("All", "*.*")])
        if not fp:
            return
        src = Path(fp)
        name = self._sanitize_style_name(src.stem)
        try:
            dst = self._styles_dir() / f"{name}.md"
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            self._append_log(f"已导入风格: {name} → {dst}")
            self._refresh_styles()
            self.style_var.set(name)
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def _new_style(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("新建风格", "请输入风格名称（字母数字- _）：", parent=self.root)
        if not name:
            return
        name = self._sanitize_style_name(name)
        if not name:
            messagebox.showerror("无效名称", "请提供有效的风格名称。")
            return
        try:
            dst = self._styles_dir() / f"{name}.md"
            if dst.exists():
                if not messagebox.askyesno("覆盖确认", f"{dst} 已存在，是否覆盖？"):
                    return
            # use current editor content or default
            txt = self._get_editor_text(self.readme_template_editor).strip() or self._default_readme_template()
            dst.write_text(txt, encoding="utf-8")
            self._append_log(f"已创建风格: {name} → {dst}")
            self._refresh_styles()
            self.style_var.set(name)
        except Exception as e:
            messagebox.showerror("创建失败", str(e))

    def _delete_style(self):
        name = self.style_var.get().strip()
        if not name:
            return
        if name == "timeline":
            messagebox.showwarning("不允许", "默认风格 timeline 不可删除。您可覆盖保存到 .cache/styles/timeline.md。")
            return
        fp_cache = self._styles_dir() / f"{self._sanitize_style_name(name)}.md"
        if not fp_cache.exists():
            messagebox.showwarning("未找到", "仅允许删除缓存目录中的风格 (.cache/styles)。内置风格请用新名称创建覆盖版本。")
            return
        if not messagebox.askyesno("确认删除", f"确定删除风格 {name} ?\n{fp_cache}"):
            return
        try:
            fp_cache.unlink()
            self._append_log(f"已删除风格: {name}")
            self._refresh_styles()
            self.style_var.set("timeline")
        except Exception as e:
            messagebox.showerror("删除失败", str(e))

    # ---------------- README template helpers ----------------
    def _scan_commit_dirs(self) -> list[Path]:
        try:
            root = Path(self.sboxes_root_var.get()).resolve()
            if root.exists() and root.is_dir():
                return [d for d in sorted(root.iterdir()) if d.is_dir()]
        except Exception:
            pass
        return []

    # Removed per-commit README editing per design: use single template only

    # ---------------- prompt helpers ----------------
    def _default_codex_prompt(self) -> str:
        return (
            "请进入到如下目录，然后根据 README.md 的要求完成指定任务，并输出‘产出目标’：\n"
            "目录：{dir}\n\n"
            "要求：\n"
            "1) 切换到该目录后阅读 README.md；\n"
            "2) 按 README 中的‘产出目标’完成对应操作（可创建/修改本目录下的 reports/figs 等文件）；\n"
            "3) 完成后将本次产出在标准输出简要列出（例如生成的 fragment.tex、图表等）；\n"
            "4) 遇到依赖缺失可做最小替代（如仅生成占位文件并标注 TODO）。\n"
        )

    def _default_latex_prompt(self) -> str:
        return (
            "请进入到{dir}，然后执行xelatex {tex}命令，帮我修复输出tex编译错误，最终生成完整的pdf文档，"
            "需反复执行{runs}次，确认最终没有bug，可容许有warning。"
            "注意，可能会碰到图片引用内容错误，这是由于图片pdf生成错误导致。需要进入到图片所在的目录，找到原始puml文件，然后，重新利用plantuml -tsvg编译，并修复错误。"
            "然后再用sips -s format pdf \"$s\" --out \"${s%.svg}.pdf\" 生成正确的pdf，以修复图片的问题。"
        )

    # 兼容说明：旧的 shards/PUML 独立提示词已合并到 tex-fix 的合并提示词，不再提供单独默认文案

    def _get_editor_text(self, widget: scrolledtext.ScrolledText) -> str:
        return widget.get("1.0", tk.END)

    def _set_editor_text(self, widget: scrolledtext.ScrolledText, text: str):
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)

    def _load_prompt_files(self):
        try:
            cp = Path(".cache/codex_prompt.txt")
            if cp.exists():
                self._set_editor_text(self.codex_prompt_editor, cp.read_text(encoding="utf-8"))
            else:
                self._set_editor_text(self.codex_prompt_editor, self._default_codex_prompt())
        except Exception:
            # widget not created yet or read failed; ignore
            pass

        try:
            lp = Path(".cache/latex_fix_prompt.txt")
            if lp.exists():
                self._set_editor_text(self.latex_prompt_editor, lp.read_text(encoding="utf-8"))
            else:
                self._set_editor_text(self.latex_prompt_editor, self._default_latex_prompt())
        except Exception:
            pass

        try:
            tfp = Path(".cache/tex_fix_prompt.txt")
            if tfp.exists():
                self._set_editor_text(self.tex_fix_prompt_editor, tfp.read_text(encoding="utf-8"))
            else:
                self._set_editor_text(self.tex_fix_prompt_editor, self._default_tex_fix_prompt())
        except Exception:
            pass

        try:
            fp = self._style_file_path(self.style_var.get())
            if fp and fp.exists():
                self._set_editor_text(self.readme_template_editor, fp.read_text(encoding="utf-8"))
            else:
                # Not present: use built-in default template
                self._set_editor_text(self.readme_template_editor, self._default_readme_template())
        except Exception:
            # Fallback to built-in default
            try:
                self._set_editor_text(self.readme_template_editor, self._default_readme_template())
            except Exception:
                pass

    def _save_codex_prompt(self):
        try:
            Path(".cache").mkdir(parents=True, exist_ok=True)
            Path(".cache/codex_prompt.txt").write_text(self._get_editor_text(self.codex_prompt_editor), encoding="utf-8")
            messagebox.showinfo("已保存", "Codex 提示词已保存到 .cache/codex_prompt.txt")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _save_latex_prompt(self):
        try:
            Path(".cache").mkdir(parents=True, exist_ok=True)
            Path(".cache/latex_fix_prompt.txt").write_text(self._get_editor_text(self.latex_prompt_editor), encoding="utf-8")
            messagebox.showinfo("已保存", "LaTeX 修复提示词已保存到 .cache/latex_fix_prompt.txt")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _save_tex_fix_prompt(self):
        try:
            Path(".cache").mkdir(parents=True, exist_ok=True)
            Path(".cache/tex_fix_prompt.txt").write_text(self._get_editor_text(self.tex_fix_prompt_editor), encoding="utf-8")
            messagebox.showinfo("已保存", "PUML+LaTeX 并行修复提示词已保存到 .cache/tex_fix_prompt.txt")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    # 旧的 shards/PUML 存储已移除（使用合并提示词或全局 LaTeX 提示词）

    def _reset_codex_prompt(self):
        try:
            self._set_editor_text(self.codex_prompt_editor, self._default_codex_prompt())
        except Exception:
            pass

    def _reset_latex_prompt(self):
        try:
            self._set_editor_text(self.latex_prompt_editor, self._default_latex_prompt())
        except Exception:
            pass

    def _reset_tex_fix_prompt(self):
        try:
            self._set_editor_text(self.tex_fix_prompt_editor, self._default_tex_fix_prompt())
        except Exception:
            pass

    # 旧的 shards/PUML 重置已移除

    def _save_readme_template(self):
        try:
            name = self._sanitize_style_name(self.style_var.get())
            if not name:
                name = "timeline"
            dst = self._styles_dir() / f"{name}.md"
            dst.write_text(self._get_editor_text(self.readme_template_editor), encoding="utf-8")
            self._append_log(f"已保存风格模板: {name} → {dst}")
            messagebox.showinfo("已保存", str(dst))
            # refresh list to ensure it appears
            self._refresh_styles()
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _reset_readme_template_default(self):
        # Reset to built-in default template
        try:
            self._set_editor_text(self.readme_template_editor, self._default_readme_template())
        except Exception:
            pass

    def _default_readme_template(self) -> str:
        return (
            "# 提交考古说明（Timeline 风格）\n\n"
            "本目录面向“某一次提交”的解读素材，采用 timeline 视角：聚焦当前提交（head）及其最多两个前置提交（head-1、head-2），以相邻提交对的 diff 作为主要证据。\n\n"
            "上下文（来自 git）\n"
            "- 提交：{sha}（{short}） — {title}\n"
            "- 作者：{author}\n"
            "- 日期：{datetime}\n"
            "- 上一提交（可选）：{prev_short}\n\n"
            "项目背景（Foxtrot 简介）\n"
            "- Foxtrot 是一个面向 STEP（ISO 10303-21）文件、覆盖从标准解析到三角化再到渲染全链路、支持本地 GUI 与 WebAssembly 的快速查看器/演示项目，使用 Rust 语言实现。\n\n"
            "目录与证据\n"
            "- 子目录：\n"
            "  - `head/`：当前提交快照（HEAD）\n"
            "  - `head-1/`：上一个提交（HEAD~1），若存在\n"
            "  - `head-2/`：上上个提交（HEAD~2），若存在\n"
            "- 差异文件（相邻对）：\n"
            "  - `HEAD.diff`：`head-1 → head` 的差异（若无 head-1，则为 `git show HEAD`）\n"
            "  - `HEAD-1.diff`：`head-2 → head-1` 的差异（若无 head-2，则为 `git show HEAD~1`）\n"
            "  - `HEAD-2.diff`：`head-3 → head-2` 的差异（若无 head-3，则为 `git show HEAD~2`）\n\n"
            "写作顺序（建议）\n"
            "1) 先读 `HEAD.diff`，用 3–5 句总结“改了什么/为什么/影响何在”（可引用具体 hunks）。\n"
            "2) 若存在 `HEAD-1.diff`/`HEAD-2.diff`，补充两点“演进脉络”：从 `head-2 → head-1 → head` 的动机与取舍。\n"
            "3) 提炼 2–3 个关键证据片段（文件+行区间），阐明对接口、数据结构、算法或边界条件的影响。\n"
            "4) 如涉及结构或算法变化，使用 PlantUML 画 1–2 张小图-中文内容。\n\n"
            "产出目标与命名规则（重要）\n"
            "- Markdown：学习摘要 + 证据摘录（来自 `HEAD*.diff`）\n"
            "- TeX：\n"
            "  - 提交报告主文件（必须）：`reports/{seq_str}-{short}.tex`（与目录名一致，如 `{seq_str}-{short}.tex`）。\n"
            "  - 图片位于figs/{seq_str}-{short}/下面，需要根据要求转成svg和pdf之后，才能引用。（重要，需要核对是否成功编译）\n\n"
            "必答清单（用证据回答）\n"
            "- 改了什么：列出 2–3 处关键改动（文件 + 行号段）。\n"
            "- 为什么改：作者意图与权衡（性能/正确性/维护性）。\n"
            "- 影响何在：对调用路径、构建、边界条件的影响与风险。\n"
            "- 如何验证：编译/测试/样例/基准的最小验证方案。\n\n"
            "TeX 片段模板示例\n"
            "```tex\n"
            "% 明确说明（非常重要），tex必须以\\section开头，不能有其他内容，不能使用begin「document」\n"
            "% (重要)tex书写规范：参考templates模版中的《LaTeX 编译常见问题与通用解决方案.md》\n"
            "\\section{提交考古：{seq_str}-{short}}\n\n"
            "\\subsection*{Commit 元信息}\n"
            "\\begin{itemize}\n"
            "  \\item 标题：{title}\n"
            "  \\item 作者：{author}\n"
            "  \\item 日期：{datetime}\n"
            "\\end{itemize}\n\n"
            "% 可选：在此小节概述本次改动的主要文件与影响点（可从 HEAD.diff 的 diffstat 中手动摘录关键行）。\n"
            "\\subsection*{变更摘要（阅读提示）}\n"
            "% 建议：从 HEAD.diff 的开头几行（包含 diffstat）手动摘取 1–3 行，帮助读者把握范围。\n\n"
            "\\subsection*{差异解读（证据）}\n"
            "% 结合 HEAD.diff / HEAD-1.diff / HEAD-2.diff，分点说明改了什么、为何而改、影响何在\n\n"
            "% 图示（必选）：若你绘制了 PlantUML 图并导出为 PDF/SVG，可在此引用\n"
            "% \\begin{figure}[h]\n"
            "%   \\centering\n"
            "%   \\includegraphics[width=0.4\\linewidth]{{{seq_str}-{short}/architecture.pdf}}\n"
            "%   \\caption{架构变化要点}\n"
            "% \\end{figure}\n"
            "```\n\n"
            "学习补充（计算几何）\n"
            "- 打开《计算几何教材.md》，按本次改动的关键词（如 orient2d/incircle/pseudo-angle/CDT 等）快速定位阅读。\n"
            "- 在 TeX 的“基础知识补充”小节，提炼不超过 200 字的要点（给出阅读路径与结论，勿展开推导），并在解读中引用对应 `HEAD*.diff` 的证据。\n\n"
            "图示生成指南\n"
            "- 环境：本机 macOS 已安装 PlantUML/Graphviz，可直接导出。\n"
            "- 路径：`figs/{seq_str}-{short}/architecture.puml` 与 `algorithm_flow.puml`。\n"
            "- 导出：\n"
            "  1) 先生成 SVG：`plantuml -tsvg -o . figs/{seq_str}-{short}/*.puml`\n"
            "  2) 再将 SVG 转为 PDF：\n"
            "     - 若有 librsvg：`for s in figs/{seq_str}-{short}/*.svg; do rsvg-convert -f pdf -o \"${s%.svg}.pdf\" \"$s\"; done`\n"
            "     - 否则（macOS）：`for s in figs/{seq_str}-{short}/*.svg; do sips -s format pdf \"$s\" --out \"${s%.svg}.pdf\"; done`\n"
            "- 引用：将导出的 PDF 放入上述目录后，按 TeX 模板引用。\n"
            "- 参考模板：见本目录下 `template/basic` 与 `template/extended`。\n\n"
            "提示：可以将本 README 作为“提示词”，连同本目录的 `HEAD*.diff` 提交给报告生成工具，自动生成初稿；再结合需求进行精炼与校对。\n"
        )

    def _default_tex_fix_prompt(self) -> str:
        return (
            "请进入到'{dir}'，优先完成图形修复与导出，然后进行 LaTeX 编译：\n"
            "一、PlantUML 修复与导出：\n"
            "1) 在 figs 子目录中查找 algorithm_flow.puml（若存在）；\n"
            "2) 执行：plantuml -tsvg algorithm_flow.puml 生成 SVG；\n"
            "3) 若出现如 'Error line N in file ...' 的错误，请打开并修复（语法、引号、未闭合括号、缺少 @startuml/@enduml 等）；\n"
            "4) 修复后再次编译确保无错误；\n"
            "5) 将 SVG 转成 PDF：优先 rsvg-convert：rsvg-convert -f pdf -o algorithm_flow.pdf algorithm_flow.svg；\n"
            "   无 rsvg-convert 时可用 macOS 的 sips：sips -s format pdf algorithm_flow.svg --out algorithm_flow.pdf；\n\n"
            "二、LaTeX 编译与修复：\n"
            "1) 使用 xelatex 编译 {tex}；\n"
            "2) 循环执行 {runs} 次或直到无错误为止（可容许 warning）；\n"
            "3) 若因图片缺失/错误导致编译失败，请回到上一步修复 PUML 并正确导出 SVG/PDF；\n\n"
            "输出要求：最终生成无错误的 PDF，必要时重复交替修复。\n\n"
            "提示：本次执行可能中断，请回顾已完成工作后继续。\n"
        )

    # ---------------- Task Executor Tab ----------------
    def _build_task_executor_tab(self, tab):
        """构建任务执行器标签页 - 整合Codex Output功能"""
        if IsolatedTaskExecutor is None:
            ttk.Label(tab, text="任务执行器模块未找到，请确保 isolated_task_executor.py 在同一目录",
                     foreground="red").pack(pady=20)
            return

        # 设置默认路径变量
        self.task_artifacts_var = tk.StringVar(value=str(Path(".artifacts")))
        self.task_workspace_var = tk.StringVar(value=str(Path(".workspace")))
        self.task_timeout_var = tk.IntVar(value=6000)  # 默认超时时间6000秒（100分钟）

        # 初始化任务执行器，传递路径参数
        self.task_executor = IsolatedTaskExecutor(
            workspace_dir=self.task_workspace_var.get(),
            artifacts_dir=self.task_artifacts_var.get()
        )
        self.task_executor_thread = None
        self.task_executor_running = False

        # 初始化Codex消息相关变量
        self.task_codex_messages = []
        self.task_codex_positions = {}  # 记录每个消息在详情视图中的位置

        # 布局 - 两列设计
        tab.rowconfigure(1, weight=1)  # 主内容区域
        tab.columnconfigure(0, weight=1)  # 左列
        tab.columnconfigure(1, weight=1)  # 右列

        # 顶部左侧：任务控制面板
        control_frame = ttk.LabelFrame(tab, text="任务控制", padding=10)
        control_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5), padx=(0, 5))
        control_frame.columnconfigure(1, weight=1)

        # 任务目录设置
        ttk.Label(control_frame, text="任务目录:").grid(row=0, column=0, sticky="w")
        ttk.Entry(control_frame, textvariable=self.task_artifacts_var).grid(row=0, column=1, sticky="ew", padx=(5, 5))
        ttk.Button(control_frame, text="浏览", command=self._browse_task_artifacts).grid(row=0, column=2)
        ttk.Button(control_frame, text="刷新列表", command=self._refresh_task_list).grid(row=0, column=3, padx=(10, 0))

        # 工作目录设置
        ttk.Label(control_frame, text="工作目录:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Entry(control_frame, textvariable=self.task_workspace_var).grid(row=1, column=1, sticky="ew", padx=(5, 5), pady=(5, 0))
        ttk.Button(control_frame, text="浏览", command=self._browse_task_workspace).grid(row=1, column=2, pady=(5, 0))

        # 项目名称设置（固定输出目录名）
        ttk.Label(control_frame, text="项目名称:").grid(row=2, column=0, sticky="w", pady=(5, 0))
        self.task_project_name_var = tk.StringVar(value="rust-project")  # 默认项目名
        project_name_entry = ttk.Entry(control_frame, textvariable=self.task_project_name_var)
        project_name_entry.grid(row=2, column=1, sticky="ew", padx=(5, 5), pady=(5, 0))
        ttk.Label(control_frame, text="(固定目录名)", foreground="#666", font=("", 9)).grid(row=2, column=2, sticky="w", padx=(5, 0), pady=(5, 0))

        # 执行超时设置（新增）
        ttk.Label(control_frame, text="超时(秒):").grid(row=3, column=0, sticky="w", pady=(5, 0))
        self.task_timeout_var = tk.IntVar(value=6000)  # 默认6000秒
        timeout_entry = ttk.Entry(control_frame, textvariable=self.task_timeout_var)
        timeout_entry.grid(row=3, column=1, sticky="ew", padx=(5, 5), pady=(5, 0))
        ttk.Label(control_frame, text="(默认6000秒)", foreground="#666", font=("", 9)).grid(row=3, column=2, sticky="w", padx=(5, 0), pady=(5, 0))

        # 执行控制按钮 - 分两行排列
        button_frame = ttk.Frame(control_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=(10, 0))

        # 第一行按钮
        button_row1 = ttk.Frame(button_frame)
        button_row1.pack(fill="x", pady=(0, 5))

        self.task_exec_single_btn = ttk.Button(button_row1, text="执行单个任务", command=self._execute_single_task)
        self.task_exec_single_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.task_exec_all_btn = ttk.Button(button_row1, text="执行所有任务", command=self._execute_all_tasks)
        self.task_exec_all_btn.pack(side=tk.LEFT, padx=5)

        self.task_stop_btn = ttk.Button(button_row1, text="停止执行", command=self._stop_task_execution, state="disabled")
        self.task_stop_btn.pack(side=tk.LEFT, padx=5)

        # 第二行按钮
        button_row2 = ttk.Frame(button_frame)
        button_row2.pack(fill="x")

        ttk.Button(button_row2, text="加载输出", command=self._load_task_output).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_row2, text="清空输出", command=self._clear_task_output).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_row2, text="🗑️ 清空项目", command=self._reset_task_status).pack(side=tk.LEFT, padx=10)

        # 第三行：从指定 commit 开始重放
        rerun_frame = ttk.Frame(control_frame)
        rerun_frame.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        rerun_frame.columnconfigure(1, weight=1)
        ttk.Label(rerun_frame, text="从指定任务ID重放:").grid(row=0, column=0, sticky="w")
        self.rerun_start_id_var = tk.StringVar(value="")
        ttk.Entry(rerun_frame, textvariable=self.rerun_start_id_var).grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(rerun_frame, text="取自选中", command=self._fill_rerun_id_from_selection).grid(row=0, column=2)
        ttk.Button(rerun_frame, text="开始重放", command=self._rerun_from_commit_gui).grid(row=0, column=3, padx=(6, 0))
        ttk.Label(rerun_frame, text="示例: 016-f620960", foreground="#666").grid(row=1, column=1, sticky="w", pady=(4,0))

        # 去除静态 Graph 工具栏（仅保留交互渲染）

        # 顶部右侧：Prompt编辑框
        prompt_frame = ttk.LabelFrame(tab, text="任务Prompt（可编辑）", padding=10)
        prompt_frame.grid(row=0, column=1, sticky="nsew", pady=(0, 5))
        prompt_frame.columnconfigure(0, weight=1)
        prompt_frame.rowconfigure(1, weight=1)  # 让文本框可以垂直扩展

        # Prompt模板选择器
        template_frame = ttk.Frame(prompt_frame)
        template_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        ttk.Label(template_frame, text="模板:").pack(side=tk.LEFT, padx=(0, 5))

        self.prompt_templates = {
            "Rust完整实现（带变量）": """请在 {workspace_dir} 内，依据 {todolist_dir}/todolist-{task_id}.tex 的提交报告，忠实复现该提交（以 HEAD 为准）的代码内容，并将结果写入固定目录 {project_dir}。

提示：当前已在 {workspace_dir}（通常为 .workspace）。可先执行 `ls -la` 查看顶层目录，确认存在 {todolist_dir} 与 {project_dir}。

一、信息收集
- 打开 tex 报告；如有，参考 {todolist_dir}/figs/{task_id}/ 下的图示（类图/序列图/流程图/状态图）
- 提取报告中出现的文件路径、模块/类名、代码片段、配置与命令；识别应新增/修改/删除的文件集合

二、代码复现
- 在 {project_dir} 内按报告还原最终文件内容：逐项创建/修改/删除文件；代码以报告中的完整片段为准
- 若片段缺失或上下文不全，填充最小可行的占位内容，并以 TODO 标注依据与缺失
- 若报告包含非 Rust 片段且已明确语言/框架，则按原语言复现；否则以 Rust 项目做最小演示，并将非 Rust 片段以资源/注释方式保存

三、构建校验
- 优先使用报告中给出的构建/运行命令；否则（若为 Rust 项目）执行 cargo build/test，并补齐必要样例

四、提交
- 在 {project_dir} 中 `git add -A` 并提交，提交信息格式："{task_id}：复现提交代码内容。"

五、复现说明
- 输出简要说明：列出复现的文件、依据的片段或图示、关键假设/妥协与验证结果

注意
- 目标是“复现报告中的代码状态”，避免超出报告范围的重构或新增设计

限制（禁止修改）
- 禁止修改以下路径/文件（它们由系统管理）：
  - {workspace_dir}/codex_error.txt
  - {workspace_dir}/codex_status.txt
  - {workspace_dir}/codex_output.txt
  - {workspace_dir}/logs/
  - {workspace_dir}/task_status.json
  - {todolist_dir}/
- 仅允许在 {project_dir}/ 目录内创建/修改/删除代码与配置。
""",

            "Rust完整实现（传统）": """请根据 report.tex 文档中描述的架构和需求，实现对应的 Rust 代码。

任务说明：
1. 仔细阅读 report.tex 文档，理解其中描述的：
   - 系统架构设计
   - 模块划分和职责
   - 数据结构定义
   - 算法流程说明
   - 接口和API设计

2. 查看 figs/ 目录中的 PlantUML 图表（.puml 文件）：
   - 类图/结构图 → 转换为 Rust struct/trait
   - 序列图 → 实现为方法调用流程
   - 流程图 → 实现为算法逻辑
   - 状态图 → 实现为状态机

3. 使用 Rust 语言实现：
   - 将 tex 中描述的数据结构转换为 Rust struct/enum
   - 将接口定义转换为 Rust trait
   - 实现文档中描述的算法和业务逻辑
   - 确保代码符合 Rust 最佳实践（ownership、借用、错误处理）
   - 添加适当的文档注释和单元测试

4. 代码组织：
   - 创建合理的模块结构（lib.rs, mod.rs）
   - 实现 Cargo.toml 配置
   - 添加必要的依赖项
   - 确保代码可编译运行

输出要求：
- 生成完整可运行的 Rust 项目代码
- 包含单元测试和集成测试
- 提供简要的实现报告说明关键设计决策""",

            "算法实现": """分析 {tex_file} 中描述的算法，使用 Rust 实现。

算法文档位置：{todolist_dir}/todolist-{task_id}.tex
图表位置：{figs_dir}

重点关注：
1. 算法的输入输出定义
2. 算法的时间空间复杂度要求
3. 边界条件和异常处理
4. 性能优化点

实现要求：
- 使用泛型提高代码复用性
- 实现 Iterator trait 以支持链式调用
- 使用 #[bench] 添加性能基准测试
- 考虑并发场景，必要时使用 Arc/Mutex
- 实现位置：{project_dir} (固定目录 {project_name})""",

            "数据结构": """将 {tex_file} 和 {figs_dir}/*.puml 中的设计转换为 Rust 代码：

1. UML类图 → Rust struct + impl
2. 接口定义 → Rust trait
3. 继承关系 → trait 实现
4. 组合关系 → struct 字段
5. 依赖关系 → 函数参数

确保：
- 所有字段都有适当的可见性（pub/pub(crate)/private）
- 实现必要的 derive（Debug, Clone, PartialEq 等）
- 使用 Builder 模式处理复杂构造
- 实现 From/Into trait 进行类型转换
- 代码位置：{project_dir} (固定目录 {project_name})""",

            "简单测试": """请读取 {tex_file} 文档，理解其描述的功能需求，然后：

1. 创建一个简单的 Rust 项目实现核心功能
2. 重点实现文档中标记为"必须"的功能
3. 为主要功能编写测试用例
4. 确保 cargo run 可以演示基本功能

项目创建位置：{project_dir} (固定目录 {project_name})
输出最小可运行版本即可。"""}

        # 设置默认模板
        self.task_prompt_template_var = tk.StringVar(value="Rust完整实现（带变量）")
        template_combo = ttk.Combobox(template_frame, textvariable=self.task_prompt_template_var,
                                      values=list(self.prompt_templates.keys()),
                                      state="readonly", width=20)
        template_combo.pack(side=tk.LEFT, padx=(0, 10))
        template_combo.bind('<<ComboboxSelected>>', lambda e: self._load_template())

        ttk.Button(template_frame, text="加载模板", command=self._load_template).pack(side=tk.LEFT)

        # Prompt文本框 - 调整高度以匹配左侧控制面板
        self.task_prompt_text = scrolledtext.ScrolledText(prompt_frame, height=12, wrap=tk.WORD)
        self.task_prompt_text.grid(row=1, column=0, sticky="nsew")

        # 优先加载保存的自定义prompt，如果不存在则加载默认模板
        self._load_saved_or_default_prompt()

        # Prompt控制按钮
        prompt_btn_frame = ttk.Frame(prompt_frame)
        prompt_btn_frame.grid(row=2, column=0, sticky="w", pady=(5, 0))

        ttk.Button(prompt_btn_frame, text="重置为当前模板", command=self._load_template).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(prompt_btn_frame, text="保存Prompt", command=self._save_task_prompt).pack(side=tk.LEFT, padx=5)

        # 参数变量说明
        help_frame = ttk.Frame(prompt_frame)
        help_frame.grid(row=3, column=0, sticky="ew", pady=(5, 0))

        help_text = ("可用变量: {workspace_dir} {todolist_dir} {project_dir}\n"
                    "{project_name} {task_id} {tex_file} {figs_dir}")
        ttk.Label(help_frame, text=help_text, foreground="#666", font=("", 9), wraplength=400).pack(anchor="w")

        # 主要内容区域（分为三部分） - 跨越两列
        main_frame = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        main_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(5, 0))

        # 左侧：任务列表
        left_frame = ttk.LabelFrame(main_frame, text="任务列表", padding=10)
        main_frame.add(left_frame, weight=1)

        # 任务列表树形控件（去掉 graph/branch 列）
        columns = ("状态", "报告", "图片")
        self.task_tree = ttk.Treeview(left_frame, columns=columns, show="tree headings", height=15)
        self.task_tree.heading("#0", text="任务ID")
        self.task_tree.heading("状态", text="状态")
        self.task_tree.heading("报告", text="报告")
        self.task_tree.heading("图片", text="图片")

        self.task_tree.column("#0", width=120)
        self.task_tree.column("状态", width=80)
        self.task_tree.column("报告", width=50)
        self.task_tree.column("图片", width=50)

        # 滚动条
        task_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=task_scroll.set)

        self.task_tree.pack(side=tk.LEFT, fill="both", expand=True)
        task_scroll.pack(side=tk.RIGHT, fill="y")

        # 中间：Graph 预览（Rust 生成，嵌入在任务列表与消息列表之间）
        graph_pane = ttk.LabelFrame(main_frame, text="Graph (Rust)", padding=6)
        main_frame.add(graph_pane, weight=1)
        graph_pane.rowconfigure(1, weight=1)
        graph_pane.columnconfigure(0, weight=1)
        gp_toolbar = ttk.Frame(graph_pane)
        gp_toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Button(gp_toolbar, text="交互渲染", command=self._interactive_graph_render_threaded).pack(side=tk.LEFT)
        gp_container = ttk.Frame(graph_pane)
        gp_container.grid(row=1, column=0, sticky="nsew")
        gp_container.rowconfigure(0, weight=1)
        gp_container.columnconfigure(0, weight=1)
        self.exec_graph_canvas = tk.Canvas(gp_container, background="#ffffff")
        self.exec_graph_canvas.grid(row=0, column=0, sticky="nsew")
        gp_ys = ttk.Scrollbar(gp_container, orient="vertical", command=self.exec_graph_canvas.yview)
        gp_xs = ttk.Scrollbar(gp_container, orient="horizontal", command=self.exec_graph_canvas.xview)
        self.exec_graph_canvas.configure(yscrollcommand=gp_ys.set, xscrollcommand=gp_xs.set)
        gp_ys.grid(row=0, column=1, sticky="ns")
        gp_xs.grid(row=1, column=0, sticky="ew")
        # 鼠标滚轮滚动
        def _gp_wheel(ev):
            try:
                delta = -1 if ev.delta > 0 else 1
                self.exec_graph_canvas.yview_scroll(delta * 3, 'units')
            except Exception:
                pass
        self.exec_graph_canvas.bind('<MouseWheel>', _gp_wheel)
        self._exec_graph_imgtk = None
        # 首次自动渲染交互图
        self.root.after(500, self._interactive_graph_render_threaded)

        # 中间：消息列表（类似Codex Output）
        middle_frame = ttk.LabelFrame(main_frame, text="消息列表", padding=10)
        main_frame.add(middle_frame, weight=1)

        # 消息列表框
        self.task_message_listbox = tk.Listbox(middle_frame, height=20)
        self.task_message_listbox.pack(side=tk.LEFT, fill="both", expand=True)

        # 绑定点击事件
        self.task_message_listbox.bind('<<ListboxSelect>>', self._on_task_message_select)

        # 滚动条
        msg_scrollbar = ttk.Scrollbar(middle_frame, orient=tk.VERTICAL, command=self.task_message_listbox.yview)
        msg_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.task_message_listbox.configure(yscrollcommand=msg_scrollbar.set)

        # 右侧：执行日志和消息详情
        right_frame = ttk.LabelFrame(main_frame, text="执行日志详情", padding=10)
        main_frame.add(right_frame, weight=2)

        self.task_log_text = scrolledtext.ScrolledText(right_frame, height=20, wrap=tk.WORD)
        self.task_log_text.pack(fill="both", expand=True)

        # 配置消息类型标签样式 - 使用白色或亮色以适应暗色背景
        self.task_log_text.tag_config("timestamp", foreground="cyan", font=("Courier", 10, "bold"))
        self.task_log_text.tag_config("user", foreground="#90EE90", background="#2a2a2a")  # 亮绿色
        self.task_log_text.tag_config("thinking", foreground="#B0B0B0", font=("Courier", 9, "italic"))  # 亮灰色
        self.task_log_text.tag_config("codex", foreground="white")  # 白色
        self.task_log_text.tag_config("error", foreground="#FF6B6B", font=("Courier", 10, "bold"))  # 亮红色
        self.task_log_text.tag_config("info", foreground="#E0E0E0")  # 浅灰色
        self.task_log_text.tag_config("success", foreground="#90EE90")  # 亮绿色
        self.task_log_text.tag_config("warning", foreground="#FFD700")  # 金色
        self.task_log_text.tag_config("separator", foreground="#808080", font=("Courier", 8))  # 中灰色

        # 底部状态栏 - 跨越两列
        status_frame = ttk.Frame(tab)
        status_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))

        self.task_status_label = ttk.Label(status_frame, text="状态: 就绪")
        self.task_status_label.pack(side=tk.LEFT)

        # 添加自动跟踪复选框
        self.task_auto_follow = tk.BooleanVar(value=True)
        ttk.Checkbutton(status_frame, text="自动跟踪最新", variable=self.task_auto_follow).pack(side=tk.LEFT, padx=(20, 0))

        self.task_progress_label = ttk.Label(status_frame, text="进度: 0/0")
        self.task_progress_label.pack(side=tk.RIGHT, padx=(0, 10))

        self.task_message_count_label = ttk.Label(status_frame, text="消息数: 0")
        self.task_message_count_label.pack(side=tk.RIGHT, padx=(0, 20))

        # 初始加载任务列表
        self.root.after(100, self._refresh_task_list)

        # 取消底部嵌入 Graph（已改为插入在任务列表与消息列表之间）

    def _fill_rerun_id_from_selection(self):
        try:
            sel = self.task_tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先在任务列表中选中一个任务")
                return
            task_id = self.task_tree.item(sel[0], "text")
            self.rerun_start_id_var.set(task_id)
        except Exception as e:
            messagebox.showerror("错误", f"读取选择失败: {e}")

    def _rerun_from_commit_gui(self):
        """GUI入口：从指定任务ID开始重放（自动新建分支→切为主分支→原主分支重命名为历史分支-时间）。"""
        if self.task_executor_running:
            messagebox.showwarning("警告", "任务正在执行中，无法重放")
            return
        raw = (self.rerun_start_id_var.get() or "").strip()
        if not raw:
            messagebox.showwarning("提示", "请先输入起始任务ID，例如 016-f620960")
            return

        # 允许仅输入数字（1/2/3 或 001/002），自动映射为完整ID（如 001-84a2fb2）
        def _normalize(user_text: str) -> Optional[str]:
            txt = (user_text or "").strip()
            # 确保执行器路径与当前 UI 同步
            self.task_executor.set_artifacts_dir(self.task_artifacts_var.get())
            self.task_executor.set_workspace_dir(self.task_workspace_var.get())
            tasks = self.task_executor.get_all_tasks()
            if not txt:
                return None
            # 若是纯数字：按序号映射（1-based）
            if txt.isdigit():
                idx = int(txt)
                if idx <= 0:
                    return None
                # tasks 已按 001.. 排序；映射 1 -> tasks[0]
                if idx - 1 < len(tasks):
                    return tasks[idx - 1]["id"]
                return None
            # 若是三位数字：以前缀匹配
            if len(txt) == 3 and all(ch.isdigit() for ch in txt):
                pref = f"{txt}-"
                for t in tasks:
                    if t["id"].startswith(pref):
                        return t["id"]
                return None
            # 若已包含连字符：尝试直接匹配或按前缀匹配
            if "-" in txt:
                ids = [t["id"] for t in tasks]
                if txt in ids:
                    return txt
                pref = txt.split("-", 1)[0] + "-"
                for t in tasks:
                    if t.startswith(pref):
                        return t
                return None
            return None

        start_id = _normalize(raw)
        if not start_id:
            messagebox.showerror("无效的任务ID", "请输入有效的任务序号（如 1 或 001）或完整ID（如 001-xxxxxxx）")
            return

        confirm = messagebox.askyesno(
            "确认",
            "将进行以下操作：\n\n"
            "1) 在项目仓库内，从该任务对应的提交创建新分支\n"
            "2) 将该分支设为主分支\n"
            "3) 原主分支重命名为 历史分支-<时间>\n\n"
            "并从该任务的下一个开始重新执行。是否继续？"
        )
        if not confirm:
            return

        # 使用后台线程执行，以避免阻塞 UI
        def _do():
            try:
                self._task_log(f"开始重放：输入={raw} → 解析起点={start_id}", "info")
                # 同步执行器路径
                self.task_executor.set_artifacts_dir(self.task_artifacts_var.get())
                self.task_executor.set_workspace_dir(self.task_workspace_var.get())
                self.task_executor.set_project_name(self.task_project_name_var.get().strip() or "rust-project")

                ok = False
                try:
                    ok = self.task_executor.rerun_from_commit(start_id, run=False)
                except Exception as e:
                    self._task_log(f"重放失败: {e}", "error")
                    ok = False
                if not ok:
                    messagebox.showerror("失败", "重放操作失败，请检查日志")
                    return

                self._task_log("✓ 分支切换与状态更新成功，开始批量执行剩余任务…", "success")
                # 开始 GUI 内的批量执行（带输出监控）
                self.root.after(0, self._execute_all_tasks)
            except Exception as e:
                self._task_log(f"重放过程错误: {e}", "error")

        threading.Thread(target=_do, daemon=True).start()

    def _browse_task_artifacts(self):
        """浏览选择任务目录"""
        path = filedialog.askdirectory(title="选择任务目录（包含 reports 和 figs）")
        if path:
            self.task_artifacts_var.set(path)
            self._refresh_task_list()

    def _browse_task_workspace(self):
        """浏览选择工作目录"""
        path = filedialog.askdirectory(title="选择工作目录")
        if path:
            self.task_workspace_var.set(path)

    def _refresh_task_list(self):
        """刷新任务列表显示（增强版：支持实时状态监控）"""
        # 清空现有列表
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)

        # 更新执行器路径 - 使用新的设置器方法
        self.task_executor.set_artifacts_dir(self.task_artifacts_var.get())
        self.task_executor.set_workspace_dir(self.task_workspace_var.get())

        # 获取任务列表
        tasks = self.task_executor.get_all_tasks()
        status = self.task_executor.status

        # 检查是否有任务正在执行（通过状态文件判断）
        current_executing_task = None
        if hasattr(self, 'current_task_id') and self.current_task_id:
            current_executing_task = self.current_task_id

        # 也检查状态文件以获取更准确的状态
        workspace_path = Path(self.task_workspace_var.get())
        status_file = workspace_path / "codex_status.txt"
        running_status = None
        if status_file.exists():
            try:
                running_status = status_file.read_text(encoding="utf-8").strip()
            except:
                pass

        for task in tasks:
            task_id = task["id"]

            # 确定状态（增强逻辑）
            if current_executing_task == task_id and running_status == "running":
                # 正在执行的任务
                status_text = "🔄 执行中..."
                tags = ("running",)
            elif task_id in status["completed"]:
                status_text = "✅ 完成"
                tags = ("completed",)
            elif task_id in status["failed"]:
                error_code = status['failed'][task_id]
                if error_code == 124:
                    status_text = "⏱️ 超时"
                    tags = ("timeout",)
                elif error_code == -1 or error_code == -15:
                    status_text = "⏹️ 中断"
                    tags = ("interrupted",)  # 使用独立的interrupted标签
                elif error_code == 127:
                    status_text = "❌ 命令未找到"
                    tags = ("failed",)
                elif error_code == 503:
                    status_text = "🚫 API错误"  # API错误显示
                    tags = ("api_error",)
                else:
                    status_text = f"❌ 失败({error_code})"
                    tags = ("failed",)
            elif task_id == status.get("current"):
                # 标记为当前但未运行
                status_text = "📍 当前"
                tags = ("current",)
            else:
                status_text = "⏳ 待执行"
                tags = ("pending",)

            # 检查文件存在
            report_exists = "✓" if task["report"].exists() else "✗"
            figs_exists = "✓" if task["figs"].exists() else "✗"
            # 已去除 graph/branch 列，不再显示

            # 添加到树形控件
            self.task_tree.insert("", "end", text=task_id, values=(status_text, report_exists, figs_exists), tags=tags)

        # 配置标签颜色（增强配色）
        self.task_tree.tag_configure("completed", foreground="#00b050")  # 深绿色
        self.task_tree.tag_configure("failed", foreground="#ff4444")     # 红色
        self.task_tree.tag_configure("api_error", foreground="#ff00ff")  # 紫色 - API错误
        self.task_tree.tag_configure("interrupted", foreground="#ff8800") # 橙色 - 中断/暂停
        self.task_tree.tag_configure("timeout", foreground="#ff6600")    # 深橙色 - 超时
        self.task_tree.tag_configure("running", foreground="#0066cc", font=("", 10, "bold"))  # 蓝色加粗
        self.task_tree.tag_configure("current", foreground="#ff8800")    # 橙色
        self.task_tree.tag_configure("pending", foreground="#888888")    # 灰色

        # 更新进度标签
        total = len(tasks)
        completed = len(status["completed"])
        failed = len(status["failed"])
        progress_text = f"进度: {completed}/{total}"
        if failed > 0:
            progress_text += f" (失败: {failed})"
        self.task_progress_label.config(text=progress_text)

        # 如果有任务正在执行，定时刷新
        if hasattr(self, 'task_executor_running') and self.task_executor_running:
            # 每2秒刷新一次任务列表以显示最新状态
            self.root.after(2000, self._refresh_task_list)


    # ---------------- Graph generation ----------------
    def _ensure_git_graph_bin(self) -> str:
        """Locate or build git-graph; return executable path."""
        import shutil, subprocess
        if getattr(self, '_git_graph_bin', None):
            return self._git_graph_bin
        # 1) env override
        p = os.environ.get("SBOXGEN_GIT_GRAPH")
        if p and Path(p).exists():
            self._git_graph_bin = p
            return p
        # 2) PATH lookup
        exe = shutil.which("git-graph")
        if exe:
            self._git_graph_bin = exe
            return exe
        # 3) local build target
        repo = Path("/Users/jqwang/104-CommitLens-codex/rust-project-01")
        cand = repo / "target/release/git-graph"
        if cand.exists():
            self._git_graph_bin = str(cand)
            return str(cand)
        # 4) attempt to build
        try:
            self._task_log("开始构建 git-graph（二进制不存在）", "info")
            subprocess.run(["cargo", "build", "--release"], cwd=str(repo), check=True)
            if cand.exists():
                self._git_graph_bin = str(cand)
                return str(cand)
        except Exception as e:
            self._task_log(f"构建 git-graph 失败: {e}", "error")
        raise RuntimeError("未找到 git-graph 可执行文件，且构建失败。请安装或修复 rust-project-01。")

    def _parse_seq_from_id(self, task_id: str) -> int:
        try:
            return int(task_id.split('-', 1)[0])
        except Exception:
            return 0

    def _find_sha_for_task(self, project_dir: Path, task_id: str) -> Optional[str]:
        try:
            # 复用执行器的查找逻辑（基于提交信息前缀）
            return self.task_executor._find_commit_by_task_id(task_id)
        except Exception:
            return None

    def _gen_graph_for_task(self, task: dict) -> bool:
        """为单个任务生成 graph.svg（Rust FFI，max_count=任务序号）。"""
        workspace = Path(self.task_workspace_var.get() or ".workspace").resolve()
        project_name = self.task_project_name_var.get().strip() or "rust-project"
        repo_dir = workspace / project_name
        if not (repo_dir / ".git").exists():
            self._task_log(f"未找到项目仓库: {repo_dir}", "error")
            return False

        # 任务序号（1-based）
        task_id = task["id"]
        try:
            idx = int(task_id.split('-', 1)[0])
        except Exception:
            idx = 0
        if idx <= 0:
            self._task_log(f"无法解析任务序号: {task_id}", "error")
            return False

        # 加载 FFI
        import ctypes as C
        dylib = os.environ.get("SBOXGEN_GG_FFI") or str(Path("/Users/jqwang/104-CommitLens-codex/rust-project-01/target/release/libgit_graph.dylib"))
        if not Path(dylib).exists():
            try:
                self._append_log("[graph] 构建 Rust FFI…")
                subprocess.run(["cargo", "build", "--release"], cwd=str(Path("/Users/jqwang/104-CommitLens-codex/rust-project-01")), check=True)
            except Exception as e:
                self._task_log(f"构建 FFI 失败: {e}", "error")
        if not Path(dylib).exists():
            self._task_log(f"未找到动态库: {dylib}", "error")
            return False
        try:
            lib = C.CDLL(dylib)
            lib.gg_render_svg.argtypes = [C.c_char_p, C.c_size_t, C.c_bool]
            lib.gg_render_svg.restype = C.c_void_p
            lib.gg_free_string.argtypes = [C.c_void_p]
            lib.gg_free_string.restype = None
        except Exception as e:
            self._task_log(f"加载 FFI 失败: {e}", "error")
            return False

        ptr = lib.gg_render_svg(str(repo_dir).encode("utf-8"), C.c_size_t(idx), C.c_bool(False))
        if not ptr:
            self._task_log(f"FFI 返回空 SVG: {task_id}", "error")
            return False
        try:
            svg_bytes = C.string_at(ptr)
        finally:
            lib.gg_free_string(ptr)

        figs_dir = task["figs"]
        try:
            figs_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        out_svg = figs_dir / "graph.svg"
        try:
            with open(out_svg, "wb") as f:
                f.write(svg_bytes)
            self._task_log(f"✓ 生成 graph: {out_svg}", "success")
            return True
        except Exception as e:
            self._task_log(f"写入 SVG 失败: {e}", "error")
            return False

    def _selected_task_ids(self) -> list[str]:
        sels = self.task_tree.selection()
        ids: list[str] = []
        for it in sels:
            tid = self.task_tree.item(it, "text")
            if tid:
                ids.append(tid)
        return ids

    def _gen_selected_graphs(self):
        ids = self._selected_task_ids()
        if not ids:
            messagebox.showinfo("提示", "请先在任务列表选择一个或多个任务")
            return
        self._gen_graphs_for_ids(ids)

    def _gen_all_graphs(self):
        tasks = self.task_executor.get_all_tasks()
        ids = [t["id"] for t in tasks]
        if not ids:
            messagebox.showinfo("提示", "未发现任务")
            return
        self._gen_graphs_for_ids(ids)

    def _gen_graphs_for_ids(self, ids: list[str]):
        if getattr(self, 'task_executor_running', False):
            self._task_log("当前有任务执行中，暂不生成 Graph", "warning")
            return
        self._task_log(f"开始批量生成 Graph：{len(ids)} 条", "info")
        def _run():
            ok = 0
            tasks_map = {t["id"]: t for t in self.task_executor.get_all_tasks()}
            for tid in ids:
                t = tasks_map.get(tid)
                if not t:
                    continue
                if self._gen_graph_for_task(t):
                    ok += 1
                # 刷新列表中该行的 graph 列显示
                try:
                    self.root.after(0, self._refresh_task_list)
                except Exception:
                    pass
            self._task_log(f"Graph 生成完成：成功 {ok}/{len(ids)}", "info")
        threading.Thread(target=_run, daemon=True).start()

    def _open_selected_graph(self):
        ids = self._selected_task_ids()
        if not ids:
            messagebox.showinfo("提示", "请先选择任务")
            return
        tid = ids[0]
        tasks_map = {t["id"]: t for t in self.task_executor.get_all_tasks()}
        t = tasks_map.get(tid)
        if not t:
            messagebox.showerror("错误", "未找到所选任务")
            return
        svg = t["figs"] / "graph.svg"
        if not svg.exists():
            messagebox.showwarning("未找到", f"未找到: {svg}")
            return
        # 打开文件（跨平台）
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", str(svg)])
            elif os.name == "nt":
                os.startfile(str(svg))  # type: ignore
            else:
                subprocess.run(["xdg-open", str(svg)])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开: {e}")

    def _preview_selected_graph_rust(self):
        ids = self._selected_task_ids()
        if not ids:
            messagebox.showinfo("提示", "请先选择任务")
            return
        tid = ids[0]
        # 找到任务
        tasks_map = {t["id"]: t for t in self.task_executor.get_all_tasks()}
        t = tasks_map.get(tid)
        if not t:
            messagebox.showerror("错误", "未找到所选任务")
            return
        # 若无 SVG，先生成
        svg = t["figs"] / "graph.svg"
        if not svg.exists():
            ok = self._gen_graph_for_task(t)
            if not ok:
                messagebox.showerror("错误", "生成 SVG 失败")
                return
        # 转 PNG 到缓存
        workspace = Path(self.task_workspace_var.get() or ".workspace").resolve()
        cache = workspace / ".graph_cache"
        cache.mkdir(parents=True, exist_ok=True)
        png_path = cache / f"{tid}.png"
        try:
            if sys.platform == "darwin":
                subprocess.run(["sips", "-s", "format", "png", str(svg), "--out", str(png_path)], check=True)
            else:
                subprocess.run(["rsvg-convert", "-f", "png", "-o", str(png_path), str(svg)], check=True)
        except Exception as e:
            self._task_log(f"PNG 转换失败: {e}", "error")
            return
        # 弹出预览窗口（可滚动）
        try:
            win = tk.Toplevel(self.root)
            win.title(f"Graph 预览 - {tid}")
            frm = ttk.Frame(win)
            frm.pack(fill="both", expand=True)
            canvas = tk.Canvas(frm, background="#ffffff")
            yscroll = ttk.Scrollbar(frm, orient="vertical", command=canvas.yview)
            xscroll = ttk.Scrollbar(frm, orient="horizontal", command=canvas.xview)
            canvas.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
            canvas.grid(row=0, column=0, sticky="nsew")
            yscroll.grid(row=0, column=1, sticky="ns")
            xscroll.grid(row=1, column=0, sticky="ew")
            frm.rowconfigure(0, weight=1)
            frm.columnconfigure(0, weight=1)
            # 显示图片
            def _display():
                self._display_png_on_canvas(canvas, png_path, attr_name='_preview_imgtk', log_prefix='[graph-preview]')
            _display()
            # 鼠标滚动
            def _on_wheel(ev):
                try:
                    delta = -1 if ev.delta > 0 else 1
                    canvas.yview_scroll(delta * 3, 'units')
                except Exception:
                    pass
            canvas.bind('<MouseWheel>', _on_wheel)
        except Exception as e:
            messagebox.showerror("错误", f"预览失败: {e}")

    def _display_png_on_canvas(self, canvas: tk.Canvas, png_path: Path, attr_name: str, log_prefix: str = ""):
        try:
            from PIL import Image, ImageTk
            img = Image.open(png_path)
            imgtk = ImageTk.PhotoImage(img)
            setattr(self, attr_name, imgtk)
            canvas.delete("all")
            canvas.create_image(0, 0, image=imgtk, anchor="nw")
            canvas.configure(scrollregion=(0, 0, img.width, img.height))
            if log_prefix:
                self._append_log(f"{log_prefix} 显示 {png_path}")
        except Exception:
            try:
                imgtk = tk.PhotoImage(file=str(png_path))
                setattr(self, attr_name, imgtk)
                canvas.delete("all")
                canvas.create_image(0, 0, image=imgtk, anchor="nw")
                canvas.configure(scrollregion=(0, 0, imgtk.width(), imgtk.height()))
                if log_prefix:
                    self._append_log(f"{log_prefix} 显示 {png_path}")
            except Exception as e2:
                if log_prefix:
                    self._append_log(f"{log_prefix} 显示 PNG 失败: {e2}")

    def _embed_repo_graph_rust_threaded(self):
        threading.Thread(target=self._embed_repo_graph_rust, daemon=True).start()

    def _embed_repo_graph_rust(self):
        """生成整库 SVG→PNG 并嵌入到任务执行页下方的画布中。"""
        workspace = Path(self.task_workspace_var.get() or ".workspace").resolve()
        project = (self.task_project_name_var.get() or "rust-project").strip() or "rust-project"
        repo = workspace / project
        if not (repo / ".git").exists():
            self._append_log(f"[exec-graph] 未找到项目仓库: {repo}")
            return
        # FFI 调用
        import ctypes as C
        dylib = os.environ.get("SBOXGEN_GG_FFI") or str(Path("/Users/jqwang/104-CommitLens-codex/rust-project-01/target/release/libgit_graph.dylib"))
        if not Path(dylib).exists():
            try:
                self._append_log("[exec-graph] 构建 Rust FFI…")
                subprocess.run(["cargo", "build", "--release"], cwd=str(Path("/Users/jqwang/104-CommitLens-codex/rust-project-01")), check=True)
            except Exception as e:
                self._append_log(f"[exec-graph] 构建失败: {e}")
        if not Path(dylib).exists():
            self._append_log(f"[exec-graph] 未找到动态库: {dylib}")
            return
        try:
            lib = C.CDLL(dylib)
            lib.gg_render_svg.argtypes = [C.c_char_p, C.c_size_t, C.c_bool]
            lib.gg_render_svg.restype = C.c_void_p
            lib.gg_free_string.argtypes = [C.c_void_p]
            lib.gg_free_string.restype = None
        except Exception as e:
            self._append_log(f"[exec-graph] 加载 FFI 失败: {e}")
            return
        ptr = lib.gg_render_svg(str(repo).encode("utf-8"), C.c_size_t(0), C.c_bool(False))
        if not ptr:
            self._append_log("[exec-graph] FFI 返回空 SVG（失败）")
            return
        try:
            svg_bytes = C.string_at(ptr)
        finally:
            lib.gg_free_string(ptr)
        cache = workspace / ".graph_cache"
        cache.mkdir(parents=True, exist_ok=True)
        svg_path = cache / "exec_graph.svg"
        png_path = cache / "exec_graph.png"
        try:
            svg_path.write_bytes(svg_bytes)
        except Exception as e:
            self._append_log(f"[exec-graph] 写入 SVG 失败: {e}")
            return
        try:
            if sys.platform == "darwin":
                subprocess.run(["sips", "-s", "format", "png", str(svg_path), "--out", str(png_path)], check=True)
            else:
                subprocess.run(["rsvg-convert", "-f", "png", "-o", str(png_path), str(svg_path)], check=True)
        except Exception as e:
            self._append_log(f"[exec-graph] SVG 转 PNG 失败: {e}")
            return
        # 显示到任务执行页嵌入画布
        self._display_png_on_canvas(self.exec_graph_canvas, png_path, attr_name='_exec_graph_imgtk', log_prefix='[exec-graph]')

    # ---------- Interactive Graph (Tk Canvas + Rust Layout JSON) ----------
    def _interactive_graph_render_threaded(self):
        threading.Thread(target=self._interactive_graph_render, daemon=True).start()

    def _interactive_graph_render(self):
        # Fetch layout JSON via FFI
        workspace = Path(self.task_workspace_var.get() or ".workspace").resolve()
        project = (self.task_project_name_var.get() or "rust-project").strip() or "rust-project"
        repo = workspace / project
        if not (repo / ".git").exists():
            self._append_log(f"[igraph] 未找到项目仓库: {repo}")
            return
        import ctypes as C, json
        dylib = os.environ.get("SBOXGEN_GG_FFI") or str(Path("/Users/jqwang/104-CommitLens-codex/rust-project-01/target/release/libgit_graph.dylib"))
        if not Path(dylib).exists():
            try:
                self._append_log("[igraph] 构建 Rust FFI…")
                subprocess.run(["cargo", "build", "--release"], cwd=str(Path("/Users/jqwang/104-CommitLens-codex/rust-project-01")), check=True)
            except Exception as e:
                self._append_log(f"[igraph] 构建失败: {e}")
        if not Path(dylib).exists():
            self._append_log(f"[igraph] 未找到动态库: {dylib}")
            return
        try:
            lib = C.CDLL(dylib)
            lib.gg_layout_json.argtypes = [C.c_char_p, C.c_size_t, C.c_bool]
            lib.gg_layout_json.restype = C.c_void_p
            lib.gg_free_string.argtypes = [C.c_void_p]
            lib.gg_free_string.restype = None
        except Exception as e:
            self._append_log(f"[igraph] 加载 FFI 失败: {e}")
            return
        ptr = lib.gg_layout_json(str(repo).encode('utf-8'), C.c_size_t(0), C.c_bool(False))
        if not ptr:
            self._append_log('[igraph] FFI 返回空 JSON')
            return
        try:
            s = C.string_at(ptr).decode('utf-8')
        finally:
            lib.gg_free_string(ptr)
        try:
            data = json.loads(s)
        except Exception as e:
            self._append_log(f"[igraph] JSON 解析失败: {e}")
            return
        # Draw into exec_graph_canvas
        self._draw_interactive_graph(self.exec_graph_canvas, data)

    def _draw_interactive_graph(self, canvas: tk.Canvas, data: dict):
        canvas.delete('all')
        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        n = len(nodes)
        if n == 0:
            return
        # Layout params
        y_step = 26
        lane_dx = 80
        x_offset = 60
        y_offset = 20
        # Build dict idx->node
        idx_map = {nd['idx']: nd for nd in nodes}
        # compute max column
        max_col = max((nd.get('column',0) for nd in nodes), default=0)
        # Draw edges (001 at top): invert y so that idx 0 (HEAD) at bottom => 001 at top if indices are HEAD-first
        # We assume indices are HEAD-first; so y = (n-1-idx)*y_step
        for e in edges:
            a = idx_map.get(e['from'])
            b = idx_map.get(e['to'])
            if not a or not b:
                continue
            x1 = x_offset + a.get('column',0)*lane_dx
            y1 = y_offset + (n-1-a['idx'])*y_step
            x2 = x_offset + b.get('column',0)*lane_dx
            y2 = y_offset + (n-1-b['idx'])*y_step
            color = e.get('color') or '#999999'
            canvas.create_line(x1, y1, x2, y2, fill=color)
        # Draw nodes and texts
        self._igraph_hitboxes = []
        for nd in nodes:
            x = x_offset + nd.get('column',0)*lane_dx
            y = y_offset + (n-1-nd['idx'])*y_step
            r = 5
            fill = nd.get('fill') or (nd.get('color') or '#007acc')
            outline = nd.get('outline') or (nd.get('color') or '#007acc')
            canvas.create_oval(x-r, y-r, x+r, y+r, fill=fill, outline=outline)
            subj = (nd.get('subject','') or '').split('\n')[0]
            if len(subj) > 60:
                subj = subj[:60] + '…'
            label = f"{nd.get('short','') } {subj} {nd.get('date','')}"
            canvas.create_text(x+10, y, anchor='w', text=label, fill='#111111', font=('',10))
            # hitbox for click
            bbox = (x-8, y-8, x+300, y+12)
            self._igraph_hitboxes.append((bbox, nd))
        # scrollregion
        width = x_offset + (max_col+1)*lane_dx + 800
        height = y_offset + n*y_step + 100
        canvas.configure(scrollregion=(0,0,width,height))
        # bind click
        def _on_click(ev):
            x,y = ev.x, ev.y
            for (bx0,by0,bx1,by1), nd in self._igraph_hitboxes:
                if bx0 <= x <= bx1 and by0 <= y <= by1:
                    # try map to task id in subject, select in list
                    import re
                    m = re.match(r"^(\d{3}-[0-9a-fA-F]{7})[：:]?", nd.get('subject',''))
                    if m:
                        self._select_task_in_list(m.group(1))
                    break
        canvas.bind('<Button-1>', _on_click)

    # ---------------- Graph Tab (Native Tk Canvas) ----------------
    def _build_graph_tab(self, tab):
        tab.rowconfigure(1, weight=1)
        tab.columnconfigure(0, weight=1)

        toolbar = ttk.Frame(tab)
        toolbar.grid(row=0, column=0, sticky="ew")

        ttk.Button(toolbar, text="交互渲染", command=self._interactive_graph_render_tab_threaded).pack(side=tk.LEFT)

        container = ttk.Frame(tab)
        container.grid(row=1, column=0, sticky="nsew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        self.graph_canvas = tk.Canvas(container, background="#ffffff")
        self.graph_canvas.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(container, orient="vertical", command=self.graph_canvas.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(container, orient="horizontal", command=self.graph_canvas.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        self.graph_canvas.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        # 初次自动渲染交互图
        self.root.after(300, self._interactive_graph_render_tab_threaded)

    def _graph_render_via_rust_threaded(self):
        threading.Thread(target=self._graph_render_via_rust, daemon=True).start()

    def _graph_render_via_rust(self):
        """Use Rust cdylib to render SVG, convert to PNG, and display in canvas."""
        workspace = Path(self.task_workspace_var.get() or ".workspace").resolve()
        project = (self.task_project_name_var.get() or "rust-project").strip() or "rust-project"
        repo = workspace / project
        if not (repo / ".git").exists():
            self._append_log(f"[graph] 未找到项目仓库: {repo}")
            return
        # Locate dylib
        dylib = os.environ.get("SBOXGEN_GG_FFI") or str(Path("/Users/jqwang/104-CommitLens-codex/rust-project-01/target/release/libgit_graph.dylib"))
        if not Path(dylib).exists():
            # try build
            try:
                self._append_log("[graph] 构建 Rust FFI…")
                subprocess.run(["cargo", "build", "--release"], cwd=str(Path("/Users/jqwang/104-CommitLens-codex/rust-project-01")), check=True)
            except Exception as e:
                self._append_log(f"[graph] 构建失败: {e}")
        if not Path(dylib).exists():
            self._append_log(f"[graph] 未找到动态库: {dylib}")
            return
        # Call FFI
        import ctypes as C
        try:
            lib = C.CDLL(dylib)
            lib.gg_render_svg.argtypes = [C.c_char_p, C.c_size_t, C.c_bool]
            lib.gg_render_svg.restype = C.c_void_p
            lib.gg_free_string.argtypes = [C.c_void_p]
            lib.gg_free_string.restype = None
        except Exception as e:
            self._append_log(f"[graph] 加载 FFI 失败: {e}")
            return
        path_b = str(repo).encode("utf-8")
        ptr = lib.gg_render_svg(path_b, C.c_size_t(0), C.c_bool(False))
        if not ptr:
            self._append_log("[graph] FFI 返回空 SVG（失败）")
            return
        try:
            svg_bytes = C.string_at(ptr)
        finally:
            lib.gg_free_string(ptr)
        try:
            cache = workspace / ".graph_cache"
            cache.mkdir(parents=True, exist_ok=True)
            svg_path = cache / "graph.svg"
            png_path = cache / "graph.png"
            with open(svg_path, "wb") as f:
                f.write(svg_bytes)
        except Exception as e:
            self._append_log(f"[graph] 写入 SVG 失败: {e}")
            return
        # Convert SVG -> PNG (prefer sips on macOS; else try rsvg-convert)
        try:
            if sys.platform == "darwin":
                subprocess.run(["sips", "-s", "format", "png", str(svg_path), "--out", str(png_path)], check=True)
            else:
                subprocess.run(["rsvg-convert", "-f", "png", "-o", str(png_path), str(svg_path)], check=True)
        except Exception as e:
            self._append_log(f"[graph] SVG 转 PNG 失败: {e}")
            return
        # Display on canvas
        self._display_png_on_canvas(self.graph_canvas, png_path, attr_name='_graph_imgtk', log_prefix='[graph]')

    def _graph_zoom(self, factor: float):
        self._graph_scale = max(0.2, min(3.0, self._graph_scale * factor))
        self._graph_redraw()

    def _graph_fit(self):
        self._graph_scale = 1.0
        self._graph_origin = (0, 0)
        self._graph_redraw()

    def _graph_on_wheel(self, event):
        try:
            if event.delta > 0:
                self._graph_zoom(1.1)
            else:
                self._graph_zoom(1/1.1)
        except Exception:
            pass

    def _graph_on_pan_start(self, event):
        self._pan_start = (event.x, event.y)
        self._pan_origin = self._graph_origin

    def _graph_on_pan_move(self, event):
        try:
            dx = (event.x - self._pan_start[0])
            dy = (event.y - self._pan_start[1])
            self._graph_origin = (self._pan_origin[0] + dx, self._pan_origin[1] + dy)
            self._graph_redraw()
        except Exception:
            pass

    def _graph_on_click(self, event):
        x = (event.x - self._graph_origin[0]) / self._graph_scale
        y = (event.y - self._graph_origin[1]) / self._graph_scale
        for n in self._graph_nodes:
            bx0, by0, bx1, by1 = n.get("bbox", (0, 0, 0, 0))
            if bx0 <= x <= bx1 and by0 <= y <= by1:
                # select in task list if possible
                tid = n.get("task_id")
                if tid:
                    self._select_task_in_list(tid)
                # highlight and redraw
                self._graph_selected_sha = n.get("sha")
                self._graph_redraw()
                break

    def _select_task_in_list(self, task_id: str):
        try:
            for item in self.task_tree.get_children():
                if self.task_tree.item(item, "text") == task_id:
                    self.task_tree.selection_set(item)
                    self.task_tree.see(item)
                    break
        except Exception:
            pass

    def _graph_refresh_threaded(self):
        threading.Thread(target=self._graph_refresh, daemon=True).start()

    def _graph_refresh(self):
        # Build commit list from .workspace/<project>
        workspace = Path(self.task_workspace_var.get() or ".workspace").resolve()
        project = (self.task_project_name_var.get() or "rust-project").strip() or "rust-project"
        repo = workspace / project
        if not (repo / ".git").exists():
            self._append_log(f"[graph] 未找到项目仓库: {repo}")
            return
        # branch prefer main
        branch = "main"
        try:
            rc = subprocess.run(["git", "show-ref", "--verify", "refs/heads/main"], cwd=str(repo))
            if rc.returncode != 0:
                cp = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo), capture_output=True, text=True)
                b = (cp.stdout or "").strip() or "HEAD"
                branch = b
        except Exception:
            pass

        # Get list of commits first-parent reversed (oldest->newest)
        try:
            cp = subprocess.run(["git", "rev-list", "--first-parent", "--reverse", branch], cwd=str(repo), capture_output=True, text=True, check=True)
            shas = [ln.strip() for ln in cp.stdout.splitlines() if ln.strip()]
        except subprocess.CalledProcessError as e:
            self._append_log(f"[graph] 获取提交失败: {e}")
            return

        # Build ref maps (branches/tags pointing exactly to sha)
        heads_map = {}
        tags_map = {}
        try:
            cp = subprocess.run(["git", "show-ref", "--heads", "--tags"], cwd=str(repo), capture_output=True, text=True, check=True)
            for ln in cp.stdout.splitlines():
                parts = ln.strip().split()
                if len(parts) != 2:
                    continue
                sha, ref = parts
                if ref.startswith("refs/heads/"):
                    heads_map.setdefault(sha, []).append(ref[len("refs/heads/"):])
                elif ref.startswith("refs/tags/"):
                    tags_map.setdefault(sha, []).append(ref[len("refs/tags/"):])
        except Exception:
            pass

        # Prepare per-commit info
        nodes = []
        tasks = self.task_executor.get_all_tasks()
        id_set = {t["id"] for t in tasks}
        pat = re.compile(r"^(\d{3}-[0-9a-fA-F]{7})[：:]?")
        for idx, sha in enumerate(shas, start=1):
            try:
                cp = subprocess.run(["git", "show", "-s", f"--format=%h%x01%H%x01%as%x01%s", sha], cwd=str(repo), capture_output=True, text=True, check=True)
                short, full, date, subject = (cp.stdout.strip().split("\x01", 3) + [""]*4)[:4]
            except Exception:
                short, full, date, subject = sha[:7], sha, "", ""
            task_id = None
            m = pat.match(subject or "")
            if m:
                tid = m.group(1)
                if tid in id_set:
                    task_id = tid
            brs = heads_map.get(sha, [])
            tgs = tags_map.get(sha, [])
            nodes.append({
                "sha": full,
                "short": short,
                "date": date,
                "subject": subject,
                "branches": brs,
                "tags": tgs,
                "task_id": task_id,
                "index": idx,
            })

        # Fetch branch lanes from git-graph --debug (authoritative)
        lanes = self._graph_fetch_branch_lanes(repo)

        self._graph_data = {"repo": str(repo), "branch": branch, "nodes": nodes, "lanes": lanes}
        self.root.after(0, self._graph_redraw)

    def _graph_redraw(self):
        c = self.graph_canvas
        c.delete("all")
        data = getattr(self, '_graph_data', None)
        if not data:
            c.create_text(20, 20, anchor="nw", text="未加载图（点击刷新）", fill="#666")
            return
        nodes = data["nodes"]
        lanes = data.get("lanes", [])
        show_br = bool(self.graph_show_branches.get())
        show_tag = bool(self.graph_show_tags.get())

        margin_top = 30
        x_line = 120
        y_step = 40
        r = 6
        scale = self._graph_scale
        ox, oy = self._graph_origin

        # title
        c.create_text(10+ox, 8+oy, anchor="nw", text=f"branch: {data['branch']}  commits: {len(nodes)}", fill="#444")

        # main line
        y0 = margin_top
        y1 = margin_top + y_step * max(0, len(nodes)-1)
        c.create_line(x_line*scale+ox, y0*scale+oy, x_line*scale+ox, y1*scale+oy, fill="#999", width=max(1, int(2*scale)))

        # draw branch lanes from git-graph (authoritative)
        lane_dx = 90
        for lane in lanes:
            col = int(lane.get("col", 0))
            name = lane.get("name", "")
            s_idx = int(lane.get("start", 1))
            e_idx = int(lane.get("end", len(nodes)))
            x = (x_line + col * lane_dx)
            y_start = margin_top + (max(1, s_idx) - 1) * y_step
            y_end = margin_top + (max(1, min(e_idx, len(nodes))) - 1) * y_step
            c.create_line(x*scale+ox, y_start*scale+oy, x*scale+ox, y_end*scale+oy, fill="#c0c0c0", dash=(4, 3), width=max(1, int(1*scale)))
            # label at start
            self._draw_badge(c, x + 10, y_start - 10, name, color="#455a64", scale=scale, ox=ox, oy=oy)

        # nodes
        self._graph_nodes = []
        sel_sha = getattr(self, '_graph_selected_sha', None)

        for i, n in enumerate(nodes):
            y = margin_top + i * y_step
            x = x_line
            fill = "#007acc" if n.get("sha") == sel_sha else "#222222"
            c.create_oval((x-r)*scale+ox, (y-r)*scale+oy, (x+r)*scale+ox, (y+r)*scale+oy, fill=fill, outline="")

            # text line
            idx = n.get("index")
            short = n.get("short", "")
            subj = (n.get("subject", "") or "").splitlines()[0]
            subj = (subj[:80] + "…") if len(subj) > 80 else subj
            date = n.get("date", "")
            tid = n.get("task_id") or ""
            left = x + 16
            text = f"[{idx:03d}] {short} {subj} {date}"
            if tid:
                text = f"{tid} | " + text
            c.create_text(left*scale+ox, y*scale+oy, anchor="w", text=text, fill="#111", font=("", max(8, int(10*scale))))

            # badges for branches/tags
            badge_x = left
            if show_br:
                for br in n.get("branches", []):
                    badge_x = self._draw_badge(c, badge_x, y+12, br, color="#2d7d2d", scale=scale, ox=ox, oy=oy)
            if show_tag:
                for tg in n.get("tags", []):
                    badge_x = self._draw_badge(c, badge_x, y+12, tg, color="#9c27b0", scale=scale, ox=ox, oy=oy)

            # hit bbox (unscaled)
            bbox = (x-10, y-10, x+500, y+22)
            meta = dict(n)
            meta["bbox"] = bbox
            self._graph_nodes.append(meta)

        # scroll region
        width = 1600
        height = (margin_top + y_step * (len(nodes)+1))
        c.configure(scrollregion=(0, 0, width*scale, height*scale))

    def _draw_badge(self, canvas: tk.Canvas, x: float, y: float, text: str, color: str, scale: float, ox: float, oy: float):
        pad_x = 6
        pad_y = 2
        tw = max(1, len(text)) * 6
        w = (tw + pad_x*2)
        h = (12 + pad_y*2)
        x0 = (x)*scale+ox
        y0 = (y)*scale+oy
        x1 = (x+w)*scale+ox
        y1 = (y+h)*scale+oy
        canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline=color)
        canvas.create_text((x+pad_x)*scale+ox, (y+pad_y-1)*scale+oy, anchor="nw", text=text, fill="#ffffff", font=("", max(6, int(8*scale))))
        return x + w + 6

    def _graph_fetch_branch_lanes(self, repo: Path) -> list:
        """Use git-graph --debug to read branch lanes (name, column, range)."""
        lanes: list[dict] = []
        # Try resolve git-graph binary, but graceful degradation if not found
        bin_path: Optional[str] = None
        try:
            bin_path = self._ensure_git_graph_bin()
        except Exception:
            # Not fatal for native graph: just return empty lanes
            return lanes
        try:
            proc = subprocess.run([bin_path, "--debug", "--no-pager"], cwd=str(repo), capture_output=True, text=True)
        except Exception:
            return lanes
        err = proc.stderr or ""
        # Parse lines like: "<name> (col <N>) (<range>) m s:<...> t:<...>"
        for ln in err.splitlines():
            ln = ln.strip()
            # fast filter
            if "(col" not in ln or ") (" not in ln:
                continue
            # name is before first ' (col'
            try:
                name, rest = ln.split(" (col ", 1)
            except ValueError:
                continue
            name = name.strip()
            # column
            try:
                col_str, rest2 = rest.split(") (", 1)
                col = int(re.findall(r"\d+", col_str)[0]) if re.findall(r"\d+", col_str) else 0
            except Exception:
                col = 0
                rest2 = rest
            # range inside next ')'
            rng_str = ""
            try:
                rng_part, _tail = rest2.split(")", 1)
                rng_str = rng_part.strip()
            except Exception:
                rng_str = rest2
            # extract first two integers as start/end
            nums = re.findall(r"\d+", rng_str)
            if len(nums) >= 2:
                s_idx, e_idx = int(nums[0]), int(nums[1])
            elif len(nums) == 1:
                s_idx, e_idx = int(nums[0]), int(nums[0])
            else:
                s_idx, e_idx = 1, 1
            lanes.append({"name": name, "col": col, "start": s_idx, "end": e_idx})
        return lanes

    def _load_saved_or_default_prompt(self):
        """优先加载保存的自定义prompt，如果不存在则加载默认模板"""
        try:
            # 首先尝试加载保存的自定义prompt
            custom_prompt_file = Path(".workspace") / "custom_prompt.txt"
            if custom_prompt_file.exists():
                custom_prompt = custom_prompt_file.read_text(encoding="utf-8").strip()
                if custom_prompt:  # 确保不是空文件
                    self.task_prompt_text.delete("1.0", tk.END)
                    self.task_prompt_text.insert("1.0", custom_prompt)
                    self._append_log(f"已加载自定义Prompt: {custom_prompt_file}")
                    return
        except Exception as e:
            self._append_log(f"加载自定义Prompt失败: {e}")

        # 如果没有保存的prompt或加载失败，则加载默认模板
        self._load_template()

    def _load_template(self):
        """加载选中的模板到编辑框"""
        template_name = self.task_prompt_template_var.get()
        if template_name in self.prompt_templates:
            self.task_prompt_text.delete("1.0", tk.END)
            self.task_prompt_text.insert("1.0", self.prompt_templates[template_name])

    def _reset_task_prompt(self, default_prompt=None):
        """重置prompt为默认值或当前模板"""
        if default_prompt:
            self.task_prompt_text.delete("1.0", tk.END)
            self.task_prompt_text.insert("1.0", default_prompt)
        else:
            self._load_template()

    def _save_task_prompt(self):
        """保存prompt到文件"""
        try:
            prompt = self.task_prompt_text.get("1.0", tk.END).strip()
            # 保存到工作目录下的custom_prompt.txt
            workspace_path = self.task_workspace_var.get() or ".workspace"
            prompt_file = Path(workspace_path) / "custom_prompt.txt"
            prompt_file.parent.mkdir(parents=True, exist_ok=True)
            prompt_file.write_text(prompt, encoding="utf-8")

            # 同时保存到.workspace目录，供下次启动时加载
            backup_file = Path(".workspace") / "custom_prompt.txt"
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            backup_file.write_text(prompt, encoding="utf-8")

            messagebox.showinfo("成功", f"Prompt已保存到:\n{prompt_file}\n{backup_file}")
            self._append_log(f"自定义Prompt已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存Prompt失败: {e}")

    def _on_task_message_select(self, event):
        """处理消息列表选择事件"""
        selection = self.task_message_listbox.curselection()
        if not selection:
            return

        index = selection[0]

        # 如果用户手动选择了非最后一条消息，暂停自动跟踪
        if event and index < self.task_message_listbox.size() - 1:
            if self.task_auto_follow.get():
                self.auto_follow_var.set(False)
                self._task_log("已暂停自动跟踪，正在查看历史消息", "info")

        # 如果选择了最后一条，恢复自动跟踪
        elif event and index == self.task_message_listbox.size() - 1:
            if not self.task_auto_follow.get():
                self.auto_follow_var.set(True)
                self._task_log("已恢复自动跟踪最新消息", "info")

        # 跳转到日志中对应的位置
        if index < len(self.task_codex_messages):
            message = self.task_codex_messages[index]

            # 如果消息有记录的位置信息，跳转到该位置
            if 'log_position' in message:
                try:
                    # 滚动到对应位置
                    self.task_log_text.see(message['log_position'])

                    # 高亮显示对应的内容
                    # 先清除之前的高亮
                    self.task_log_text.tag_remove("message_highlight", "1.0", tk.END)

                    # 查找消息内容在日志中的位置
                    search_text = message.get('content', message.get('title', ''))
                    if search_text:
                        # 从记录的位置开始搜索
                        start_pos = message['log_position']
                        found_pos = self.task_log_text.search(
                            search_text[:50],  # 搜索前50个字符
                            start_pos,
                            stopindex=tk.END,
                            nocase=True
                        )

                        if found_pos:
                            # 计算结束位置
                            end_pos = f"{found_pos}+{len(search_text)}c"

                            # 添加高亮标签
                            self.task_log_text.tag_add("message_highlight", found_pos, end_pos)
                            self.task_log_text.tag_config("message_highlight", background="#ffff99")

                            # 确保高亮部分可见
                            self.task_log_text.see(found_pos)
                except Exception as e:
                    print(f"跳转到日志位置失败: {e}")
            else:
                # 如果没有位置信息，尝试搜索消息内容
                try:
                    # 获取消息的时间戳
                    timestamp = message.get('timestamp', '')
                    if 'T' in timestamp and len(timestamp) > 11:
                        search_timestamp = timestamp[11:19]  # 提取 HH:MM:SS
                    else:
                        search_timestamp = timestamp[:8] if len(timestamp) > 8 else timestamp

                    # 搜索时间戳在日志中的位置
                    if search_timestamp:
                        found_pos = self.task_log_text.search(
                            f"[{search_timestamp}]",
                            "1.0",
                            stopindex=tk.END
                        )

                        if found_pos:
                            self.task_log_text.see(found_pos)

                            # 高亮该消息段
                            self.task_log_text.tag_remove("message_highlight", "1.0", tk.END)

                            # 找到下一个时间戳或分隔线的位置作为结束
                            next_timestamp = self.task_log_text.search(
                                "[",
                                f"{found_pos}+1line",
                                stopindex=tk.END
                            )

                            if next_timestamp:
                                self.task_log_text.tag_add("message_highlight", found_pos, f"{next_timestamp}-1c")
                            else:
                                # 如果没有找到下一个时间戳，高亮到下一个分隔线或末尾
                                self.task_log_text.tag_add("message_highlight", found_pos, f"{found_pos}+5lines")

                            self.task_log_text.tag_config("message_highlight", background="#ffff99")

                except Exception as e:
                    print(f"搜索日志位置失败: {e}")

    def _parse_task_codex_content(self, content: str):
        """解析Codex输出内容为结构化消息"""
        self.task_codex_messages = []
        lines = content.split('\n')

        current_message = None
        current_content = []

        for i, line in enumerate(lines):
            # 检测带时间戳的消息行
            if line.startswith('[') and ']' in line and 'T' in line[:30]:
                # 保存上一个消息
                if current_message and current_content:
                    current_message['content'] = '\n'.join(current_content).strip()
                    if current_message['content']:  # 只保存有内容的消息
                        self.task_codex_messages.append(current_message)
                    current_content = []

                # 解析新消息
                bracket_end = line.index(']') + 1
                timestamp = line[1:bracket_end-1]
                rest = line[bracket_end:].strip()

                # 确定消息类型
                msg_type = "info"
                if "User" in rest or "User instructions" in rest:
                    msg_type = "user"
                elif "thinking" in rest.lower():
                    msg_type = "thinking"
                elif "exec" in rest or "bash" in rest:
                    msg_type = "exec"
                elif "succeeded" in rest:
                    msg_type = "success"
                elif "failed" in rest or "ERROR" in rest:
                    msg_type = "error"
                elif "codex" in rest.lower():
                    msg_type = "codex"
                elif "tokens used" in rest:
                    msg_type = "tokens"

                current_message = {
                    'timestamp': timestamp,
                    'type': msg_type,
                    'content': rest if rest else ''
                }

                # 如果当前行还有内容，添加到内容中
                if rest:
                    current_content = [rest]
                else:
                    current_content = []
            else:
                # 继续添加内容行
                if line.strip():  # 只添加非空行
                    current_content.append(line)

        # 保存最后一个消息
        if current_message and current_content:
            current_message['content'] = '\n'.join(current_content).strip()
            if current_message['content']:
                self.task_codex_messages.append(current_message)

        return self.task_codex_messages

    def _update_task_message_list(self):
        """更新消息列表显示"""
        self.task_message_listbox.delete(0, tk.END)

        for msg in self.task_codex_messages:
            # 提取时间部分（HH:MM:SS）
            timestamp = msg['timestamp']
            if 'T' in timestamp and len(timestamp) > 11:
                timestamp = timestamp[11:19]  # 提取HH:MM:SS部分
            elif len(timestamp) > 8:
                timestamp = timestamp[:8]

            # 根据类型显示不同的图标
            type_icon = {
                'user': '👤',
                'thinking': '🤔',
                'exec': '⚡',
                'success': '✅',
                'error': '❌',
                'codex': '🤖',
                'tokens': '🎫',
                'info': 'ℹ️'
            }.get(msg['type'], '📝')

            # 截取内容的前50个字符作为预览
            content = msg.get('content', '')
            preview = content[:50].replace('\n', ' ')
            if len(content) > 50:
                preview += '...'

            # 添加到列表
            display_text = f"[{timestamp}] {type_icon} {preview}"
            self.task_message_listbox.insert(tk.END, display_text)

        # 更新消息计数
        self.task_message_count_label.config(text=f"消息数: {len(self.task_codex_messages)}")

        # 如果自动跟踪，选择最后一个
        if self.task_auto_follow.get() and self.task_codex_messages:
            self.task_message_listbox.selection_clear(0, tk.END)
            self.task_message_listbox.selection_set(len(self.task_codex_messages) - 1)
            self.task_message_listbox.see(tk.END)

    def _append_message_to_detail_view(self, message):
        """流式添加消息到详情视图（复用Codex Output的实时更新策略）"""
        # 如果是第一条消息，清空详情视图
        if len(self.task_codex_messages) == 1:
            self.task_log_text.delete(1.0, tk.END)
            self.task_codex_positions = {}

        # 记录起始位置
        start_line = int(self.task_log_text.index(tk.END).split('.')[0])

        # 如果不是第一条消息，添加分隔符
        if len(self.task_codex_messages) > 1:
            self.task_log_text.insert(tk.END, "-" * 80 + "\n\n", "separator")

        # 时间戳
        timestamp = message['timestamp']
        if 'T' in timestamp and len(timestamp) > 11:
            timestamp = timestamp[11:19]

        # 添加时间戳和类型
        type_label = {
            'user': 'User',
            'thinking': 'Thinking',
            'exec': 'Execute',
            'success': 'Success',
            'error': 'Error',
            'codex': 'Codex',
            'tokens': 'Tokens',
            'info': 'Info',
            'status': 'Status'
        }.get(message['type'], 'Unknown')

        self.task_log_text.insert(tk.END, f"[{timestamp}] {type_label}:\n", "timestamp")

        # 添加内容
        content = message.get('content', '')
        if content:
            self.task_log_text.insert(tk.END, content + "\n", message['type'])

        # 记录结束位置
        end_line = int(self.task_log_text.index(tk.END).split('.')[0])
        msg_index = len(self.task_codex_messages) - 1
        self.task_codex_positions[msg_index] = (start_line, end_line)

        # 如果自动跟踪，滚动到底部
        if self.task_auto_follow.get():
            self.task_log_text.see(tk.END)

        self.root.update_idletasks()

    def _update_message_in_detail_view(self, index, message):
        """更新详情视图中的特定消息（用于流式内容累积）"""
        if index not in self.task_codex_positions:
            # 如果位置不存在，添加新消息
            self._append_message_to_detail_view(message)
            return

        # 获取消息在详情视图中的位置
        start_line, end_line = self.task_codex_positions[index]

        # 删除旧内容（保留标题行）
        self.task_log_text.delete(f"{start_line + 1}.0", f"{end_line}.0")

        # 插入新内容
        content = message.get('content', '')
        if content:
            self.task_log_text.insert(f"{start_line + 1}.0", content + "\n", message['type'])

        # 更新结束位置
        new_end_line = start_line + 1 + content.count('\n') + 1
        self.task_codex_positions[index] = (start_line, new_end_line)

        # 更新后续消息的位置
        line_diff = new_end_line - end_line
        if line_diff != 0:
            for i in range(index + 1, len(self.task_codex_messages)):
                if i in self.task_codex_positions:
                    old_start, old_end = self.task_codex_positions[i]
                    self.task_codex_positions[i] = (old_start + line_diff, old_end + line_diff)

        # 如果自动跟踪，保持在底部
        if self.task_auto_follow.get():
            self.task_log_text.see(tk.END)

        self.root.update_idletasks()

    def _populate_task_detail_view(self):
        """填充详情视图，所有消息连续显示"""
        self.task_log_text.delete(1.0, tk.END)
        self.task_codex_positions = {}  # 重置位置记录

        for i, msg in enumerate(self.task_codex_messages):
            # 记录起始位置
            start_line = int(self.task_log_text.index(tk.END).split('.')[0])

            # 时间戳
            timestamp = msg['timestamp']
            if 'T' in timestamp and len(timestamp) > 11:
                timestamp = timestamp[11:19]

            # 添加时间戳和类型
            type_label = {
                'user': 'User',
                'thinking': 'Thinking',
                'exec': 'Execute',
                'success': 'Success',
                'error': 'Error',
                'codex': 'Codex',
                'tokens': 'Tokens',
                'info': 'Info'
            }.get(msg['type'], 'Unknown')

            self.task_log_text.insert(tk.END, f"[{timestamp}] {type_label}:\n", "timestamp")

            # 添加内容
            content = msg.get('content', '')
            if content:
                self.task_log_text.insert(tk.END, content + "\n", msg['type'])

            # 添加分隔线
            self.task_log_text.insert(tk.END, "-" * 80 + "\n\n", "separator")

            # 记录结束位置
            end_line = int(self.task_log_text.index(tk.END).split('.')[0])
            self.task_codex_positions[i] = (start_line, end_line)

        # 如果自动跟踪，滚动到底部
        if self.task_auto_follow.get():
            self.task_log_text.see(tk.END)

    def _task_log(self, msg, tag="info"):
        """添加日志到任务执行日志窗口"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.task_log_text.insert(tk.END, f"[{timestamp}] {msg}\n", tag)
        self.task_log_text.see(tk.END)
        self.root.update_idletasks()

    def _execute_single_task(self):
        """执行单个任务"""
        if self.task_executor_running:
            messagebox.showwarning("警告", "任务正在执行中")
            return

        self.task_executor_running = True
        self.task_exec_single_btn.config(state="disabled")
        self.task_exec_all_btn.config(state="disabled")
        self.task_stop_btn.config(state="normal")

        def run():
            try:
                self._task_log("开始执行单个任务...", "info")

                # 获取下一个任务
                task = self.task_executor.get_next_task()
                if not task:
                    self._task_log("所有任务已完成！", "success")
                    return

                # 设置当前执行的任务ID
                self.current_task_id = task["id"]
                self.task_executor.status["current"] = task["id"]
                self.task_executor.save_status()

                # 立即刷新任务列表以显示正在执行状态
                self.root.after(0, self._refresh_task_list)

                self._task_log(f"执行任务: {task['id']}", "info")

                # 准备工作空间
                self.task_executor.prepare_workspace(task)
                self._task_log(f"工作空间已准备: {self.task_executor.current_dir}", "info")

                # 确保API key被传递给执行器
                self._ensure_api_key_for_executor()

                # 获取prompt：优先使用编辑框中的内容（可能是保存的或修改的）
                custom_prompt = self.task_prompt_text.get("1.0", tk.END).strip()

                # 如果编辑框为空，尝试加载保存的prompt
                if not custom_prompt:
                    try:
                        # 先尝试从工作目录加载
                        workspace_path = self.task_workspace_var.get() or ".workspace"
                        prompt_file = Path(workspace_path) / "custom_prompt.txt"
                        if prompt_file.exists():
                            custom_prompt = prompt_file.read_text(encoding="utf-8").strip()
                            self._task_log(f"使用保存的自定义Prompt: {prompt_file}", "info")
                        else:
                            # 尝试从备份位置加载
                            backup_file = Path(".workspace") / "custom_prompt.txt"
                            if backup_file.exists():
                                custom_prompt = backup_file.read_text(encoding="utf-8").strip()
                                self._task_log(f"使用备份的自定义Prompt: {backup_file}", "info")
                    except Exception as e:
                        self._task_log(f"加载自定义Prompt失败: {e}", "warning")

                # 如果还是没有prompt，使用当前选择的模板
                if not custom_prompt:
                    template_name = self.task_prompt_template_var.get()
                    if template_name in self.prompt_templates:
                        custom_prompt = self.prompt_templates[template_name]
                        self._task_log(f"使用模板Prompt: {template_name}", "info")
                    else:
                        self._task_log("警告：没有找到有效的Prompt，使用默认模板", "warning")
                        custom_prompt = self.prompt_templates["Rust完整实现（带变量）"]

                result = self._execute_task_with_prompt(task, custom_prompt)
                success = result[0] if isinstance(result, tuple) else result
                error_code = result[1] if isinstance(result, tuple) else (0 if success else 1)

                if success:
                    self.task_executor.status["completed"].append(task["id"])
                    self._task_log(f"任务 {task['id']} 执行成功", "success")
                    # 成功后：在 {project_name} 目录内提交结果
                    try:
                        if self.task_executor.commit_results(task):
                            self._task_log("已创建提交（见项目目录）", "success")
                        else:
                            self._task_log("提交失败（已忽略）", "warning")
                    except Exception as e:
                        self._task_log(f"提交时发生异常（已忽略）: {e}", "warning")
                    # 音效已在_execute_task_with_prompt中处理
                else:
                    # 保存具体的错误码而不是失败次数
                    self.task_executor.status["failed"][task["id"]] = error_code
                    if error_code == -1:
                        self._task_log(f"任务 {task['id']} 被中断", "warning")
                    else:
                        self._task_log(f"任务 {task['id']} 执行失败 (错误码: {error_code})", "error")
                    # 音效已在_execute_task_with_prompt中处理

                # 清理工作空间
                self.task_executor.cleanup_workspace()
                self.task_executor.save_status()

                # 清除当前任务ID
                self.current_task_id = None

            except Exception as e:
                self._task_log(f"执行出错: {e}", "error")
                self._play_notification_sound(False)
            finally:
                # 清除当前任务ID
                self.current_task_id = None
                self.task_executor_running = False
                self.root.after(0, self._on_task_execution_complete)

        self.task_executor_thread = threading.Thread(target=run, daemon=True)
        self.task_executor_thread.start()

    def _execute_all_tasks(self):
        """执行所有任务"""
        if self.task_executor_running:
            messagebox.showwarning("警告", "任务正在执行中")
            return

        if not messagebox.askyesno("确认", "确定要执行所有未完成的任务吗？"):
            return

        self.task_executor_running = True
        self.task_exec_single_btn.config(state="disabled")
        self.task_exec_all_btn.config(state="disabled")
        self.task_stop_btn.config(state="normal")

        def run():
            try:
                self._task_log("开始批量执行任务...", "info")

                while self.task_executor_running:
                    task = self.task_executor.get_next_task()
                    if not task:
                        self._task_log("所有任务已完成！", "success")
                        break

                    # 设置当前执行的任务ID
                    self.current_task_id = task["id"]
                    self.task_executor.status["current"] = task["id"]
                    self.task_executor.save_status()

                    # 立即刷新任务列表以显示正在执行状态
                    self.root.after(0, self._refresh_task_list)

                    self._task_log(f"\n{'='*50}", "info")
                    self._task_log(f"执行任务: {task['id']}", "info")

                    try:
                        # 准备工作空间
                        self.task_executor.prepare_workspace(task)
                        self._task_log(f"工作空间已准备", "info")

                        # 确保API key被传递给执行器
                        self._ensure_api_key_for_executor()

                        # 获取prompt：优先使用编辑框中的内容（可能是保存的或修改的）
                        custom_prompt = self.task_prompt_text.get("1.0", tk.END).strip()

                        # 如果编辑框为空，尝试加载保存的prompt
                        if not custom_prompt:
                            try:
                                # 先尝试从工作目录加载
                                workspace_path = self.task_workspace_var.get() or ".workspace"
                                prompt_file = Path(workspace_path) / "custom_prompt.txt"
                                if prompt_file.exists():
                                    custom_prompt = prompt_file.read_text(encoding="utf-8").strip()
                                    self._task_log(f"使用保存的自定义Prompt: {prompt_file}", "info")
                                else:
                                    # 尝试从备份位置加载
                                    backup_file = Path(".workspace") / "custom_prompt.txt"
                                    if backup_file.exists():
                                        custom_prompt = backup_file.read_text(encoding="utf-8").strip()
                                        self._task_log(f"使用备份的自定义Prompt: {backup_file}", "info")
                            except Exception as e:
                                self._task_log(f"加载自定义Prompt失败: {e}", "warning")

                        # 如果还是没有prompt，使用当前选择的模板
                        if not custom_prompt:
                            template_name = self.task_prompt_template_var.get()
                            if template_name in self.prompt_templates:
                                custom_prompt = self.prompt_templates[template_name]
                                self._task_log(f"使用模板Prompt: {template_name}", "info")
                            else:
                                self._task_log("警告：没有找到有效的Prompt，使用默认模板", "warning")
                                custom_prompt = self.prompt_templates["Rust完整实现（带变量）"]

                        result = self._execute_task_with_prompt(task, custom_prompt)
                        success = result[0] if isinstance(result, tuple) else result
                        error_code = result[1] if isinstance(result, tuple) else (0 if success else 1)

                        if success:
                            self.task_executor.status["completed"].append(task["id"])
                            self._task_log(f"任务 {task['id']} 执行成功", "success")
                            # 成功后：在 {project_name} 目录内提交结果
                            try:
                                if self.task_executor.commit_results(task):
                                    self._task_log("已创建提交（见项目目录）", "success")
                                else:
                                    self._task_log("提交失败（已忽略）", "warning")
                            except Exception as e:
                                self._task_log(f"提交时发生异常（已忽略）: {e}", "warning")
                            # 音效已在_execute_task_with_prompt中处理
                        else:
                            # 保存具体的错误码而不是失败次数
                            self.task_executor.status["failed"][task["id"]] = error_code
                            if error_code == -1:
                                self._task_log(f"任务 {task['id']} 被中断", "warning")
                            else:
                                self._task_log(f"任务 {task['id']} 执行失败 (错误码: {error_code})", "error")
                            # 音效已在_execute_task_with_prompt中处理

                        # 清理工作空间
                        self.task_executor.cleanup_workspace()
                        self.task_executor.save_status()

                        # 刷新列表显示
                        self.root.after(0, self._refresh_task_list)

                        # 等待间隔
                        if self.task_executor_running:
                            self._task_log(f"等待5秒后执行下一个任务...", "info")
                            time.sleep(5)

                    except Exception as e:
                        self._task_log(f"任务 {task['id']} 执行异常: {e}", "error")

                # 批量执行完成，播放一次总体状态音效
                completed_count = len(self.task_executor.status["completed"])
                failed_count = len(self.task_executor.status["failed"])

                if completed_count > 0 and failed_count == 0:
                    self._task_log(f"✅ 所有任务完成！成功: {completed_count}", "success")
                    self._play_notification_sound(True)
                elif completed_count > 0:
                    self._task_log(f"⚠️ 部分完成。成功: {completed_count}, 失败: {failed_count}", "warning")
                    self._play_notification_sound(True)  # 有成功的也播放成功音
                else:
                    self._task_log(f"❌ 全部失败。失败: {failed_count}", "error")
                    self._play_notification_sound(False)

            except Exception as e:
                self._task_log(f"批量执行出错: {e}", "error")
                self._play_notification_sound(False)
            finally:
                # 清除当前任务ID
                self.current_task_id = None
                self.task_executor_running = False
                self.root.after(0, self._on_task_execution_complete)

        self.task_executor_thread = threading.Thread(target=run, daemon=True)
        self.task_executor_thread.start()

    def _stop_task_execution(self):
        """停止任务执行"""
        try:
            self.task_executor_running = False
            self._task_log("正在停止任务执行...", "warning")

            # 清除当前任务ID
            if hasattr(self, 'current_task_id'):
                self.current_task_id = None

            # 停止文件监控
            if hasattr(self, 'task_monitoring'):
                self.task_monitoring = False

            # 终止正在运行的子进程
            if hasattr(self, 'task_exec_process') and self.task_exec_process:
                try:
                    if self.task_exec_process.poll() is None:  # 进程仍在运行
                        if os.name == "posix":
                            # Unix系统：尝试发送SIGTERM
                            try:
                                # 先尝试直接terminate
                                self.task_exec_process.terminate()
                                self._task_log("已发送终止信号", "info")

                                # 等待1秒
                                try:
                                    self.task_exec_process.wait(timeout=1)
                                    self._task_log("进程已优雅终止", "success")
                                except subprocess.TimeoutExpired:
                                    # 如果还没退出，尝试发送到进程组
                                    try:
                                        pgid = os.getpgid(self.task_exec_process.pid)
                                        os.killpg(pgid, signal.SIGTERM)
                                        self._task_log("已发送终止信号到进程组", "info")
                                        # 再等待1秒
                                        self.task_exec_process.wait(timeout=1)
                                    except (ProcessLookupError, PermissionError, OSError) as e:
                                        # 进程组可能已经结束或没有权限
                                        self._task_log(f"无法终止进程组: {e}", "warning")
                                        # 最后尝试强制kill
                                        try:
                                            self.task_exec_process.kill()
                                            self._task_log("进程已强制终止", "warning")
                                        except:
                                            pass
                            except (ProcessLookupError, PermissionError, OSError) as e:
                                self._task_log(f"进程可能已经结束: {e}", "info")
                        else:
                            # Windows系统
                            self.task_exec_process.terminate()
                            # 等待2秒让进程优雅退出
                            try:
                                self.task_exec_process.wait(timeout=2)
                                self._task_log("进程已优雅终止", "success")
                            except subprocess.TimeoutExpired:
                                # 如果还没退出，强制杀死
                                self.task_exec_process.kill()
                                self._task_log("进程已强制终止", "warning")
                    else:
                        self._task_log("进程已经结束", "info")

                    # 更新状态文件
                    try:
                        workspace_path = self.task_workspace_var.get()
                        if workspace_path:
                            status_file = Path(workspace_path) / "codex_status.txt"
                            if status_file.exists():
                                status_file.write_text("interrupted", encoding="utf-8")
                    except Exception as e:
                        self._task_log(f"更新状态文件失败: {e}", "warning")

                    self.task_exec_process = None
                    self._task_log("任务执行已停止", "warning")
                except Exception as e:
                    self._task_log(f"停止进程时出错: {e}", "error")
                    # 确保清理进程引用
                    self.task_exec_process = None
            else:
                self._task_log("没有正在运行的任务进程", "info")

            # 更新UI状态
            if hasattr(self, 'task_status_label'):
                self.task_status_label.config(text="状态: ⏹️ 已停止")

            # 更新任务执行器状态，将当前任务标记为中断
            if hasattr(self, 'current_task_id') and self.current_task_id:
                # 将当前任务标记为中断（返回码-1）
                self.task_executor.status["failed"][self.current_task_id] = -1
                self.task_executor.save_status()
                self._task_log(f"任务 {self.current_task_id} 已标记为中断", "warning")

            # 刷新任务列表
            self.root.after(100, self._refresh_task_list)

        except Exception as e:
            # 捕获所有异常，避免程序崩溃
            self._task_log(f"停止执行时发生错误: {e}", "error")
            import traceback
            traceback.print_exc()
            # 确保重置状态
            self.task_executor_running = False
            if hasattr(self, 'task_exec_process'):
                self.task_exec_process = None
            if hasattr(self, 'current_task_id'):
                self.current_task_id = None

    def _on_task_execution_complete(self):
        """任务执行完成回调"""
        self.task_exec_single_btn.config(state="normal")
        self.task_exec_all_btn.config(state="normal")
        self.task_stop_btn.config(state="disabled")
        self._refresh_task_list()
        # 保持最终执行状态，不立即重置为"就绪"
        # 让用户看到最终执行结果

    def _reset_task_status(self):
        """重置任务执行状态并清空整个项目"""
        if self.task_executor_running:
            messagebox.showwarning("警告", "任务正在执行中，无法重置")
            return

        # 获取项目目录路径
        workspace_path = self.task_workspace_var.get()
        project_name = self.task_project_name_var.get().strip() or "rust-project"

        if not workspace_path:
            messagebox.showwarning("警告", "请先设置工作目录")
            return

        project_dir = Path(workspace_path) / project_name
        todolist_dir = Path(workspace_path) / "todolist"

        # 构建提示信息
        msg = "确定要重置所有任务状态并清空项目吗？\n\n将执行以下操作：\n"
        msg += "1. 清除所有任务完成/失败记录\n"
        msg += "2. 清空输出文件 (codex_output.txt等)\n"

        if project_dir.exists():
            msg += f"3. 删除项目目录: {project_dir.name}/\n"
        if todolist_dir.exists():
            msg += f"4. 删除任务目录: todolist/\n"

        msg += "5. 重新创建项目目录并初始化 Git 仓库 (git init)\n"
        msg += "\n⚠️ 此操作不可恢复！"

        if not messagebox.askyesno("确认重置", msg, icon='warning'):
            return

        try:
            # 1. 重置任务状态
            self.task_executor.status = {
                "completed": [],
                "failed": {},
                "current": None,
                "last_execution": None
            }
            self.task_executor.save_status()
            self._task_log("✓ 任务状态已重置", "success")

            # 2. 清空输出文件
            output_file = Path(workspace_path) / "codex_output.txt"
            error_file = Path(workspace_path) / "codex_error.txt"
            status_file = Path(workspace_path) / "codex_status.txt"

            for file, name in [(output_file, "codex_output.txt"),
                              (error_file, "codex_error.txt"),
                              (status_file, "codex_status.txt")]:
                if file.exists():
                    file.write_text("", encoding="utf-8")
                    self._task_log(f"✓ 已清空: {name}", "info")

            # 3. 删除项目目录
            if project_dir.exists():
                import shutil
                shutil.rmtree(project_dir)
                self._task_log(f"✓ 已删除项目目录: {project_name}/", "warning")

            # 4. 删除todolist目录
            if todolist_dir.exists():
                import shutil
                shutil.rmtree(todolist_dir)
                self._task_log(f"✓ 已删除任务目录: todolist/", "warning")

            # 5. 清空日志目录
            log_dir = Path(workspace_path) / "logs"
            if log_dir.exists():
                log_count = 0
                for log_file in log_dir.glob("*.log"):
                    log_file.unlink()
                    log_count += 1
                if log_count > 0:
                    self._task_log(f"✓ 已清空 {log_count} 个日志文件", "info")

            # 6. 清空UI显示
            self.task_codex_messages = []
            self.task_message_listbox.delete(0, tk.END)
            self.task_log_text.delete(1.0, tk.END)
            self.task_codex_positions = {}
            if hasattr(self, 'task_output_position'):
                self.task_output_position = 0

            # 7. 停止监控（如果正在运行）
            if hasattr(self, 'task_monitoring') and self.task_monitoring:
                self.task_monitoring = False
                self._task_log("✓ 已停止文件监控", "info")

            # 8. 重新创建项目目录并初始化 Git（幂等）
            try:
                project_dir.mkdir(parents=True, exist_ok=True)
                if not (project_dir / ".git").exists():
                    subprocess.run(["git", "init"], cwd=str(project_dir), check=True)
                    self._task_log(f"✓ 已初始化 Git 仓库: {project_dir}", "info")
                else:
                    self._task_log(f"ℹ️ 已存在 Git 仓库: {project_dir}", "info")
            except Exception as e:
                self._task_log(f"Git 初始化失败（忽略继续）: {e}", "warning")

            # 9. 刷新任务列表
            self._refresh_task_list()

            # 显示完成信息
            self._task_log("="*50, "separator")
            self._task_log("🔄 项目已完全重置！", "success")
            self._task_log(f"工作目录: {workspace_path}", "info")
            self._task_log(f"项目目录: {project_name}/ (已重新创建并初始化 Git)", "info")
            self._task_log("您可以开始新的任务执行", "info")
            self._task_log("="*50, "separator")

            messagebox.showinfo("重置完成",
                              f"项目已完全重置\n\n"
                              f"• 任务状态已清空\n"
                              f"• 项目目录已删除\n"
                              f"• 输出文件已清理\n\n"
                              f"可以开始新的迭代开发")

        except PermissionError as e:
            self._task_log(f"权限错误: {e}", "error")
            messagebox.showerror("权限错误",
                               f"无法删除某些文件/目录\n"
                               f"可能有文件正在被使用\n\n"
                               f"错误: {e}")
        except Exception as e:
            self._task_log(f"重置过程出错: {e}", "error")
            messagebox.showerror("错误", f"重置失败: {e}")

    def _execute_task_with_prompt(self, task, custom_prompt):
        """使用自定义prompt执行任务，并实时解析输出（复用Codex Output策略）"""
        import subprocess
        import threading
        import time  # 导入time模块用于缓冲区管理

        self._task_log(f"准备执行任务 {task['id']}...", "info")

        # 存储进程引用以支持停止功能
        self.task_exec_process = None

        # 更新执行器的工作目录设置
        workspace_path = self.task_workspace_var.get()
        if workspace_path != str(self.task_executor.workspace_dir):
            self._task_log(f"🔄 切换工作目录: {self.task_executor.workspace_dir} → {workspace_path}", "warning")
            self.task_executor.set_workspace_dir(workspace_path)
            self._task_log(f"✅ 工作目录已切换到: {workspace_path}", "success")
        else:
            self._task_log(f"📁 使用当前工作目录: {workspace_path}", "info")

        # 设置项目名称
        project_name = self.task_project_name_var.get().strip() or "rust-project"
        self.task_executor.set_project_name(project_name)
        self._task_log(f"📦 项目输出目录: {workspace_path}/{project_name}/", "info")

        # 清空消息列表和日志区
        self.task_codex_messages = []
        self.task_message_listbox.delete(0, tk.END)
        self.task_log_text.delete(1.0, tk.END)
        self.task_codex_positions = {}  # 清空位置记录
        self.task_message_count_label.config(text="消息数: 0")  # 重置计数

        # 显示初始执行信息
        initial_info = f"=== 执行任务: {task['id']} ===\n"
        initial_info += f"工作目录: {workspace_path}\n"
        initial_info += f"项目输出: {project_name}/\n"
        initial_info += f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        initial_info += "=" * 80 + "\n\n"
        self.task_log_text.insert(tk.END, initial_info, "info")

        # 准备工作空间
        self.task_executor.prepare_workspace(task)
        self._task_log(f"工作空间已准备: {self.task_executor.workspace_dir}", "info")
        self._task_log(f"任务文件位于: {self.task_executor.workspace_dir}/todolist/", "info")

        # 确保API key被设置
        self._ensure_api_key_for_executor()

        # 使用变量替换处理prompt
        processed_prompt = self.task_executor._substitute_prompt_variables(custom_prompt, task)

        # 添加任务ID到prompt末尾
        full_prompt = f"{processed_prompt}\n\n任务ID: {task['id']}"

        # 记录执行的prompt（包括变量替换信息）
        self._task_log("执行Prompt (已替换变量):", "info")
        self.task_log_text.insert(tk.END, full_prompt + "\n", "thinking")
        self.task_log_text.insert(tk.END, "-" * 80 + "\n", "separator")

        # 准备环境变量
        env = os.environ.copy()

        # 构建执行命令
        cmd = [
            "codex", "exec",
            "--skip-git-repo-check",
            "--sandbox", "workspace-write",
            "--model", "gpt-5-codex-high",
            full_prompt
        ]

        # 准备输出文件（复用Codex Output策略）
        output_file = self.task_executor.workspace_dir / "codex_output.txt"
        error_file = self.task_executor.workspace_dir / "codex_error.txt"
        status_file = self.task_executor.workspace_dir / "codex_status.txt"

        # 处理文件：output追加，error和status覆盖
        if not output_file.exists():
            output_file.write_text("", encoding="utf-8")
        error_file.write_text("", encoding="utf-8")
        status_file.write_text("running", encoding="utf-8")

        # 记录初始文件位置用于增量读取
        self.task_output_position = output_file.stat().st_size if output_file.exists() else 0
        self.task_monitoring = True  # 启动监控标志

        try:
            # 启动进程 - 在工作空间根目录执行
            # 在POSIX系统上创建新进程组，便于安全终止
            kwargs = {
                "cwd": str(self.task_executor.workspace_dir),  # 在工作空间根目录执行
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "text": True,
                "env": env,
                "bufsize": 1
            }

            # 在Unix系统上创建新进程组
            if os.name == "posix":
                kwargs["start_new_session"] = True

            self.task_exec_process = subprocess.Popen(cmd, **kwargs)
            process = self.task_exec_process  # 保持向后兼容

            # 实时读取输出的线程
            output_lines = []
            error_lines = []
            self.task_current_buffer = []  # 用于累积当前消息内容
            self.task_current_message = None  # 当前正在构建的消息

            def read_output():
                """流式读取并追加输出到文件（简化版，类似Codex Output）"""
                try:
                    while self.task_executor_running:
                        line = process.stdout.readline()
                        if not line:
                            break

                        output_lines.append(line)
                        # 追加到输出文件（不覆盖）
                        with open(output_file, "a", encoding="utf-8") as f:
                            f.write(line)
                            f.flush()

                        # 不在这里处理解析，让监控线程处理
                except Exception as e:
                    print(f"读取输出错误: {e}")

            def read_error():
                """流式读取错误输出"""
                try:
                    while self.task_executor_running:  # 检查运行标志
                        line = process.stderr.readline()
                        if not line:
                            break
                        error_lines.append(line)
                        # 追加到错误文件
                        with open(error_file, "a", encoding="utf-8") as f:
                            f.write(line)
                            f.flush()
                        self._task_log(f"错误: {line.strip()}", "error")
                except:
                    pass

            # 启动读取线程
            output_thread = threading.Thread(target=read_output, daemon=True)
            error_thread = threading.Thread(target=read_error, daemon=True)
            output_thread.start()
            error_thread.start()

            # 启动文件监控线程（监控status和error文件变化）
            monitor_thread = threading.Thread(
                target=self._monitor_task_files,
                args=(output_file, error_file, status_file),
                daemon=True
            )
            monitor_thread.start()

            # 等待进程完成（使用UI配置的超时时间）
            try:
                # 从 UI 控件获取超时时间（默认6000秒）
                timeout_seconds = self.task_timeout_var.get() if hasattr(self, 'task_timeout_var') else 6000
                self._task_log(f"🕑 设置执行超时时间: {timeout_seconds}秒", "info")
                return_code = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                # 超时处理
                timeout_minutes = timeout_seconds // 60
                self._task_log(f"⚠️ 任务执行超过{timeout_minutes}分钟（{timeout_seconds}秒），正在终止...", "warning")
                if process.poll() is None:
                    process.kill()
                return_code = 124

            # 检查是否被手动停止（需要在判断返回码之前检查）
            if not self.task_executor_running:
                # 用户手动停止了执行
                return_code = -1  # 标记为被中断
                self._task_log("任务被用户中断", "warning")
                status_file.write_text("interrupted", encoding="utf-8")
            elif return_code == -15:  # SIGTERM
                # 接收到SIGTERM信号
                return_code = -1  # 标记为被中断
                self._task_log("任务被终止信号中断", "warning")
                status_file.write_text("interrupted", encoding="utf-8")

            # 等待线程完成
            output_thread.join(timeout=1)
            error_thread.join(timeout=1)
            self.task_monitoring = False  # 停止监控

            # 等待监控线程完成
            if monitor_thread.is_alive():
                monitor_thread.join(timeout=2)

            # 写入最终状态（在API错误检测后可能会被覆盖）
            status_file.write_text(str(return_code), encoding="utf-8")

            # 更新最终状态显示（复用Codex Output的状态更新逻辑）
            if return_code == 0:
                final_status = "✅ 执行成功"
            elif return_code == -1:
                final_status = "⏹️ 用户中断"
            elif return_code == 124:
                final_status = "⏱️ 执行超时"
            elif return_code == 127:
                final_status = "❌ 找不到命令"
            elif return_code == 503:
                final_status = "🚫 API错误"  # 新增503状态
            elif return_code == -15:
                final_status = "⏹️ 被终止"
            else:
                final_status = f"⚠️ 退出码 {return_code}"

            self.root.after(0, lambda: self.task_status_label.config(text=f"状态: {final_status}"))

            # 保存完整输出到日志
            full_output = ''.join(output_lines)
            full_error = ''.join(error_lines)

            # 确保日志目录存在
            log_dir = self.task_executor.log_dir
            if not log_dir.exists():
                log_dir.mkdir(parents=True, exist_ok=True)

            # 日志文件
            log_file = log_dir / f"{task['id']}.log"
            try:
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(f"=== 任务 {task['id']} 执行日志 ===\n")
                    f.write(f"时间: {datetime.now()}\n")
                    f.write(f"Prompt:\n{full_prompt}\n")
                    f.write(f"\n=== 输出 ===\n")
                    f.write(full_output)
                    if full_error:
                        f.write(f"\n=== 错误 ===\n")
                        f.write(full_error)
                    f.write(f"\n=== 最终状态 ===\n")
                    f.write(f"返回码: {return_code}\n")
                    f.write(f"状态: {final_status}\n")
                self._task_log(f"日志已保存: {log_file.name}", "info")
            except Exception as e:
                self._task_log(f"保存日志失败: {e}", "error")

            # 最后清理一些资源
            self.task_current_message = None
            self.task_current_buffer = []

            # 检查输出中是否包含API错误或其他已知错误模式
            api_error_detected = False
            # 更精确的 API/服务错误模式（大小写不敏感），仅检查末尾若干行，避免早期无害报错误伤
            error_patterns = [
                "we're currently experiencing high demand",
                "rate limit exceeded",
                "too many requests",
                "api key is invalid",
                "invalid api key",
                "unauthorized",
                "service unavailable",
                "503 service unavailable",
                "bad gateway",
                "502 bad gateway",
                "authentication failed",
                "certificate verify failed",
            ]
            exclude_patterns = [
                # 常见无害/过程性报错，不视为 API 错误
                "no such file or directory",
                "os error",
                "exec error",
                "not found",
            ]

            # 仅扫描输出末尾 15 行，且大小写不敏感
            try:
                tail = "\n".join(full_output.splitlines()[-15:])
            except Exception:
                tail = full_output
            hay = tail.lower()
            if return_code == 0:
                hit = any(pat in hay for pat in error_patterns)
                excl = any(pat in hay for pat in exclude_patterns)
                if hit and not excl:
                    api_error_detected = True
                    self._task_log("⚠️ 检测到可能的 API/服务错误（尾部日志）", "error")
                    return_code = 503
                    status_file.write_text("503", encoding="utf-8")

            # 根据返回码判断成功/失败，返回(success, error_code)
            if return_code == 0:
                self._task_log(f"任务 {task['id']} 执行成功", "success")
                # 播放成功提示音（复用Codex Output）
                self._play_notification_sound(success=True)
                return (True, 0)
            elif return_code == 503:
                # API错误
                self._task_log(f"任务 {task['id']} 执行失败：API错误", "error")
                self.root.after(0, lambda: self.task_status_label.config(text="状态: 🚫 API错误"))
                self._play_notification_sound(success=False)
                return (False, 503)
            elif return_code == -1 or return_code == -15:
                self._task_log(f"任务 {task['id']} 被用户中断", "warning")
                # 不播放失败音，因为这是用户主动操作
                return (False, -1)  # 返回中断状态码
            else:
                self._task_log(f"任务 {task['id']} 执行失败，返回码: {return_code}", "error")
                # 播放失败提示音
                self._play_notification_sound(success=False)
                return (False, return_code)

        except subprocess.TimeoutExpired:
            process.kill()
            status_file.write_text("124", encoding="utf-8")  # 超时状态码
            self._task_log(f"任务 {task['id']} 执行超时（5分钟）", "error")
            self.root.after(0, lambda: self.task_status_label.config(text="状态: ⏱️ 执行超时"))
            self._play_notification_sound(success=False)
            return (False, 124)
        except Exception as e:
            self._task_log(f"任务 {task['id']} 执行出错: {e}", "error")
            if status_file.exists():
                status_file.write_text("1", encoding="utf-8")  # 一般错误状态码
            self.root.after(0, lambda: self.task_status_label.config(text="状态: ❌ 执行失败"))
            self._play_notification_sound(success=False)
            return (False, 1)
        finally:
            # 确保所有监控都停止
            self.task_monitoring = False  # 确保停止监控

            # 清理进程引用
            if hasattr(self, 'task_exec_process') and self.task_exec_process:
                # 确保进程已经完全终止
                if self.task_exec_process.poll() is None:
                    try:
                        self.task_exec_process.wait(timeout=2)  # 再等2秒确保进程完全结束
                    except subprocess.TimeoutExpired:
                        self.task_exec_process.kill()  # 强制终止
                        try:
                            self.task_exec_process.wait(timeout=1)
                        except:
                            pass

            self.task_exec_process = None

            # 等待一小段时间，确保所有文件操作都完成
            import time
            time.sleep(0.5)

            # 现在可以安全地清理工作空间
            try:
                self.task_executor.cleanup_workspace()
                self._task_log("工作空间已清理", "info")
            except Exception as e:
                self._task_log(f"清理工作空间失败: {e}", "error")

    def _monitor_task_files(self, output_file, error_file, status_file):
        """监控任务执行文件变化（完全复用Codex Output监控策略）"""
        import time
        from pathlib import Path

        # 记录上一次的状态和错误内容，避免重复处理
        last_error_content = ""
        last_status = ""

        # 用于记录已处理的错误哈希，避免重复
        self.task_last_error_hash = ""

        # 消息解析缓冲区
        message_buffer = ""

        while self.task_monitoring and self.task_executor_running:  # 检查两个标志
            try:
                # 监控status文件（复用Codex Output的_check_status_and_error_files逻辑）
                if status_file.exists():
                    status = status_file.read_text(encoding="utf-8").strip()
                    if status and status != last_status:
                        last_status = status

                        # 构建状态文本（与Codex Output保持一致）
                        if status == "running":
                            status_text = "🔄 运行中..."
                        elif status == "0":
                            status_text = "✅ 执行成功"
                        elif status == "124":
                            status_text = "⏱️ 执行超时"
                        elif status == "127":
                            status_text = "❌ 找不到命令"
                        elif status == "interrupted":
                            status_text = "⏹️ 已中断"
                        elif status == "-1":
                            status_text = "⏹️ 用户中断"
                        elif status == "-15":
                            status_text = "⏹️ 被终止"
                        else:
                            try:
                                code = int(status)
                                if code < 0:
                                    status_text = f"⏹️ 信号 {abs(code)}"
                                else:
                                    status_text = f"⚠️ 退出码 {status}"
                            except:
                                status_text = f"⚠️ 状态: {status}"

                        # 更新主状态栏
                        self.root.after(0, lambda st=status_text: self.task_status_label.config(text=f"状态: {st}"))

                # 监控error文件（简化版）
                if error_file.exists():
                    error_content = error_file.read_text(encoding="utf-8").strip()
                    if error_content and error_content != last_error_content:
                        last_error_content = error_content
                        # 直接在日志区显示错误
                        error_display = f"\n❌ 错误输出:\n{error_content[:500]}\n"
                        self.root.after(0, lambda content=error_display: self._append_to_log_detail(content))

                # 监控output文件增量（改进版：同时更新消息列表和日志）
                if output_file.exists():
                    current_size = output_file.stat().st_size
                    if current_size > self.task_output_position:
                        # 读取新增内容
                        with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                            f.seek(self.task_output_position)
                            new_content = f.read()
                            self.task_output_position = current_size

                            if new_content:
                                # 记录当前日志位置（用于消息定位）
                                current_log_position = None
                                try:
                                    current_log_position = self.task_log_text.index("end-1c")
                                except:
                                    pass

                                # 1. 直接显示在日志详情区
                                self.root.after(0, lambda content=new_content: self._append_to_log_detail(content))

                                # 2. 处理消息解析（带缓冲和位置记录）
                                message_buffer += new_content

                                # 尝试解析完整的消息（按行分割，保留不完整的行）
                                lines = message_buffer.split('\n')

                                # 如果最后一行不是空的，说明可能不完整，保留它
                                if lines and lines[-1]:
                                    message_buffer = lines[-1]
                                    lines = lines[:-1]
                                else:
                                    message_buffer = ""

                                # 解析完整的行（传递日志位置）
                                if lines:
                                    complete_content = '\n'.join(lines)
                                    self._parse_and_update_messages_with_position(complete_content, current_log_position)

            except Exception as e:
                print(f"监控文件出错: {e}")

            # 每0.3秒检查一次，平衡响应性和性能
            time.sleep(0.3)

    def _parse_and_update_messages_with_position(self, content, log_position):
        """轻量级解析内容并更新消息列表（带位置记录）"""
        try:
            lines = content.split('\n')
            messages_to_add = []

            for line in lines:
                if not line.strip():
                    continue

                # 检测是否是带时间戳的消息行
                if line.startswith('[') and 'T' in line[:30] and ']' in line[:30]:
                    try:
                        bracket_end = line.index(']')
                        timestamp = line[1:bracket_end]
                        rest = line[bracket_end+1:].strip()

                        # 确定消息类型
                        msg_type = "info"
                        title = "信息"

                        if "User" in rest or "User instructions" in rest:
                            msg_type = "user"
                            title = "用户指令"
                        elif "thinking" in rest.lower():
                            msg_type = "thinking"
                            title = "AI 思考"
                        elif "exec" in rest or "bash" in rest:
                            msg_type = "exec"
                            title = "执行命令"
                        elif "succeeded" in rest:
                            msg_type = "success"
                            title = "执行成功"
                        elif "failed" in rest or "ERROR" in rest:
                            msg_type = "error"
                            title = "执行失败"
                        elif "codex" in rest.lower():
                            msg_type = "codex"
                            title = "Codex 输出"
                        elif "tokens used" in rest:
                            msg_type = "tokens"
                            title = "Token 使用"

                        # 创建简单的消息对象（带位置信息）
                        message = {
                            'timestamp': timestamp,
                            'type': msg_type,
                            'title': title,
                            'content': rest[:100] + '...' if len(rest) > 100 else rest
                        }

                        # 如果有日志位置，记录它
                        if log_position:
                            message['log_position'] = log_position

                        messages_to_add.append(message)

                    except Exception as e:
                        # 忽略解析错误，继续处理其他行
                        pass

            # 批量更新UI（在主线程中）
            if messages_to_add:
                self.root.after(0, self._batch_add_messages_to_list, messages_to_add)

        except Exception as e:
            print(f"解析消息错误: {e}")

    def _parse_and_update_messages(self, content):
        """轻量级解析内容并更新消息列表"""
        try:
            lines = content.split('\n')
            messages_to_add = []

            for line in lines:
                if not line.strip():
                    continue

                # 检测是否是带时间戳的消息行
                if line.startswith('[') and 'T' in line[:30] and ']' in line[:30]:
                    try:
                        bracket_end = line.index(']')
                        timestamp = line[1:bracket_end]
                        rest = line[bracket_end+1:].strip()

                        # 确定消息类型
                        msg_type = "info"
                        title = "信息"

                        if "User" in rest or "User instructions" in rest:
                            msg_type = "user"
                            title = "用户指令"
                        elif "thinking" in rest.lower():
                            msg_type = "thinking"
                            title = "AI 思考"
                        elif "exec" in rest or "bash" in rest:
                            msg_type = "exec"
                            title = "执行命令"
                        elif "succeeded" in rest:
                            msg_type = "success"
                            title = "执行成功"
                        elif "failed" in rest or "ERROR" in rest:
                            msg_type = "error"
                            title = "执行失败"
                        elif "codex" in rest.lower():
                            msg_type = "codex"
                            title = "Codex 输出"
                        elif "tokens used" in rest:
                            msg_type = "tokens"
                            title = "Token 使用"

                        # 创建简单的消息对象
                        message = {
                            'timestamp': timestamp,
                            'type': msg_type,
                            'title': title,
                            'content': rest[:100] + '...' if len(rest) > 100 else rest
                        }

                        messages_to_add.append(message)

                    except Exception as e:
                        # 忽略解析错误，继续处理其他行
                        pass

            # 批量更新UI（在主线程中）
            if messages_to_add:
                self.root.after(0, self._batch_add_messages_to_list, messages_to_add)

        except Exception as e:
            print(f"解析消息错误: {e}")

    def _batch_add_messages_to_list(self, messages):
        """批量添加消息到列表框"""
        try:
            for message in messages:
                # 如果消息没有位置信息，尝试获取当前日志位置
                if 'log_position' not in message:
                    try:
                        message['log_position'] = self.task_log_text.index("end-1c")
                    except:
                        pass

                # 添加到消息数组
                self.task_codex_messages.append(message)

                # 提取时间（HH:MM:SS）
                timestamp = message['timestamp']
                if 'T' in timestamp and len(timestamp) > 11:
                    timestamp = timestamp[11:19]
                elif len(timestamp) > 8:
                    timestamp = timestamp[:8]

                # 根据类型选择图标
                icon = {
                    'user': '👤',
                    'thinking': '🤔',
                    'exec': '⚡',
                    'success': '✅',
                    'error': '❌',
                    'codex': '🤖',
                    'tokens': '🎫',
                    'info': 'ℹ️'
                }.get(message['type'], '📝')

                # 构建显示文本
                content = message.get('content', '')
                preview = content[:50].replace('\n', ' ')
                if len(content) > 50:
                    preview += '...'

                display_text = f"[{timestamp}] {icon} {message['title']}"
                if preview:
                    display_text += f": {preview}"

                # 添加到列表框
                self.task_message_listbox.insert(tk.END, display_text)

                # 设置颜色
                index = self.task_message_listbox.size() - 1
                color_map = {
                    'error': '#d32f2f',
                    'success': '#388e3c',
                    'thinking': '#7c4dff',
                    'exec': '#00695c',
                    'codex': '#ff6b35'
                }
                if message['type'] in color_map:
                    self.task_message_listbox.itemconfig(index, {'fg': color_map[message['type']]})

            # 更新消息计数
            self.task_message_count_label.config(text=f"消息数: {len(self.task_codex_messages)}")

            # 如果启用自动跟踪，选择最后一条消息
            if self.task_auto_follow.get() and self.task_message_listbox.size() > 0:
                self.task_message_listbox.see(tk.END)
                self.task_message_listbox.selection_clear(0, tk.END)
                self.task_message_listbox.selection_set(self.task_message_listbox.size() - 1)

        except Exception as e:
            print(f"批量添加消息错误: {e}")

    def _add_single_message_to_list(self, index, msg):
        """添加单个消息到列表框"""
        try:
            # 提取时间（HH:MM:SS）
            timestamp = msg['timestamp']
            if 'T' in timestamp and len(timestamp) > 11:
                timestamp = timestamp[11:19]
            elif len(timestamp) > 8:
                timestamp = timestamp[:8]

            # 根据类型选择图标
            icon = {
                'user': '👤',
                'thinking': '🤔',
                'exec': '⚡',
                'success': '✅',
                'error': '❌',
                'codex': '🤖',
                'tokens': '🎫',
                'info': 'ℹ️'
            }.get(msg['type'], '📝')

            # 构建显示文本
            display_text = f"[{timestamp}] {icon} {msg['title']}"
            if msg.get('content'):
                preview = msg['content'][:50].replace('\n', ' ')
                if len(msg['content']) > 50:
                    preview += '...'
                display_text += f": {preview}"

            # 添加到列表框
            self.task_message_listbox.insert(tk.END, display_text)

            # 设置颜色
            color_map = {
                'error': '#d32f2f',
                'success': '#388e3c',
                'thinking': '#7c4dff',
                'exec': '#00695c',
                'codex': '#ff6b35'
            }
            if msg['type'] in color_map:
                self.task_message_listbox.itemconfig(index, {'fg': color_map[msg['type']]})

            # 更新消息计数
            self.task_message_count_label.config(text=f"消息数: {len(self.task_codex_messages)}")

            # 如果启用自动跟踪，选择最后一条消息
            if self.task_auto_follow.get():
                self.task_message_listbox.see(tk.END)
                self.task_message_listbox.selection_clear(0, tk.END)
                self.task_message_listbox.selection_set(tk.END)

        except Exception as e:
            print(f"添加消息到列表错误: {e}")

    def _append_to_log_detail(self, content):
        """简单地追加内容到日志详情区（避免复杂解析）"""
        try:
            # 直接插入内容
            self.task_log_text.insert(tk.END, content)

            # 自动滚动到底部
            if self.task_auto_follow.get():
                self.task_log_text.see(tk.END)

            # 限制文本大小（避免内存溢出）
            lines = int(self.task_log_text.index('end-1c').split('.')[0])
            if lines > 5000:  # 最多保留5000行
                self.task_log_text.delete('1.0', f'{lines-4000}.0')
        except Exception as e:
            print(f"追加日志详情错误: {e}")

    def _process_codex_line_streaming(self, line):

        # 检测是否是新消息开始
        if line.startswith('[') and 'T' in line[:30] and ']' in line[:30]:
            # 先完成上一个消息
            if self.task_current_message:
                self._finalize_current_message()

            # 解析新消息
            try:
                bracket_end = line.index(']') + 1
                timestamp = line[1:bracket_end-1]
                rest = line[bracket_end:].strip()

                # 确定消息类型
                msg_type = self._determine_message_type(rest)

                # 创建新消息
                self.task_current_message = {
                    'timestamp': timestamp,
                    'type': msg_type,
                    'content': rest if rest else ''
                }
                self.task_current_buffer = [rest] if rest else []

                # 立即添加到列表（即使内容还在累积）
                self._add_message_to_list(self.task_current_message)

            except Exception as e:
                print(f"解析消息头失败: {e}")
        elif line.strip() and self.task_current_message:
            # 添加到当前消息内容
            self.task_current_buffer.append(line.rstrip())
            # 更新当前消息内容
            self.task_current_message['content'] = '\n'.join(self.task_current_buffer)
            # 更新消息列表中的显示
            self._update_current_message_display()

    def _determine_message_type(self, text):
        """根据文本内容确定消息类型"""
        if "User" in text or "User instructions" in text:
            return "user"
        elif "thinking" in text.lower():
            return "thinking"
        elif "exec" in text or "bash" in text:
            return "exec"
        elif "succeeded" in text:
            return "success"
        elif "failed" in text or "ERROR" in text:
            return "error"
        elif "codex" in text.lower():
            return "codex"
        elif "tokens used" in text:
            return "tokens"
        else:
            return "info"

    def _write_to_log_detail(self, line):
        """写入日志详情视图"""
        if not line.strip():
            return

        # 根据内容类型设置标签
        if line.startswith("[") and "T" in line[:30] and "]" in line[:30]:
            # 带时间戳的消息头
            if "User:" in line:
                tag = "user"
            elif "thinking" in line.lower():
                tag = "thinking"
            elif "exec" in line:
                tag = "exec"
            elif "succeeded" in line:
                tag = "success"
            elif "failed" in line or "ERROR" in line:
                tag = "error"
            elif "codex" in line.lower():
                tag = "codex"
            else:
                tag = "info"
        else:
            # 普通内容行
            tag = "info"

        self.task_log_text.insert(tk.END, line, tag)

        # 自动滚动
        if self.task_auto_follow.get():
            self.task_log_text.see(tk.END)
        self.root.update_idletasks()

    def _finalize_current_message(self):
        """完成当前消息并添加到列表"""
        if self.task_current_message:
            # 更新内容
            if self.task_current_buffer:
                self.task_current_message['content'] = '\n'.join(self.task_current_buffer)

            # 如果消息还没在列表中，添加它
            if self.task_current_message not in self.task_codex_messages:
                self.task_codex_messages.append(self.task_current_message)
                self._update_task_message_list()
                # 更新详情视图
                self._append_message_to_detail_view(self.task_current_message)
            else:
                # 如果消息已存在，更新详情视图中的内容
                try:
                    index = self.task_codex_messages.index(self.task_current_message)
                    self._update_message_in_detail_view(index, self.task_current_message)
                except ValueError:
                    pass

            # 重置
            self.task_current_message = None
            self.task_current_buffer = []

    def _add_message_to_list(self, message):
        """添加消息到列表并立即显示"""
        # 添加到消息数组
        if message not in self.task_codex_messages:
            self.task_codex_messages.append(message)

        # 更新显示
        self._update_single_message_display(len(self.task_codex_messages) - 1, message)

        # 同时更新详情视图（流式更新）
        self._append_message_to_detail_view(message)

    def _update_single_message_display(self, index, msg):
        """更新单个消息在列表中的显示"""
        # 格式化显示文本
        timestamp = msg['timestamp']
        if 'T' in timestamp and len(timestamp) > 11:
            timestamp = timestamp[11:19]
        elif len(timestamp) > 8:
            timestamp = timestamp[:8]

        # 根据类型显示图标
        type_icon = {
            'user': '👤',
            'thinking': '🤔',
            'exec': '⚡',
            'success': '✅',
            'error': '❌',
            'codex': '🤖',
            'tokens': '🎫',
            'info': 'ℹ️'
        }.get(msg['type'], '📝')

        # 截取内容预览
        content = msg.get('content', '')
        preview = content[:50].replace('\n', ' ')
        if len(content) > 50:
            preview += '...'

        # 构建显示文本
        display_text = f"[{timestamp}] {type_icon} {preview}"

        # 如果是当前索引，更新它；否则插入新项
        if index < self.task_message_listbox.size():
            # 更新现有项
            self.task_message_listbox.delete(index)
            self.task_message_listbox.insert(index, display_text)
        else:
            # 添加新项
            self.task_message_listbox.insert(tk.END, display_text)

        # 更新消息计数
        self.task_message_count_label.config(text=f"消息数: {len(self.task_codex_messages)}")

        # 自动跟踪
        if self.task_auto_follow.get():
            self.task_message_listbox.see(tk.END)
            # 选中最新消息
            self.task_message_listbox.selection_clear(0, tk.END)
            if self.task_message_listbox.size() > 0:
                self.task_message_listbox.selection_set(self.task_message_listbox.size() - 1)

    def _update_current_message_display(self):
        """更新当前正在累积的消息显示"""
        if self.task_current_message:
            # 找到消息在列表中的索引
            try:
                index = self.task_codex_messages.index(self.task_current_message)
                self._update_single_message_display(index, self.task_current_message)
                # 更新详情视图中的当前消息
                self._update_message_in_detail_view(index, self.task_current_message)
            except ValueError:
                # 消息不在列表中，添加它
                self._add_message_to_list(self.task_current_message)

    def _load_task_output(self):
        """加载已存在的Codex输出文件"""
        workspace_path = self.task_workspace_var.get()
        if not workspace_path:
            messagebox.showwarning("警告", "请先设置工作目录")
            return

        output_file = Path(workspace_path) / "codex_output.txt"
        error_file = Path(workspace_path) / "codex_error.txt"
        status_file = Path(workspace_path) / "codex_status.txt"

        if not output_file.exists():
            self._task_log("未找到输出文件，可能还未执行过任务", "warning")
            return

        try:
            # 清空现有消息
            self.task_codex_messages = []
            self.task_message_listbox.delete(0, tk.END)
            self.task_log_text.delete(1.0, tk.END)

            # 读取输出文件
            with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 解析内容
            self._parse_task_codex_content(content)
            self._update_task_message_list()
            # 重新填充详情视图（因为是加载历史内容）
            self._populate_task_detail_view()

            # 读取状态文件（复用Codex Output的状态文本）
            if status_file.exists():
                status = status_file.read_text(encoding="utf-8").strip()
                if status == "0":
                    status_text = "✅ 上次执行成功"
                elif status == "124":
                    status_text = "⏱️ 上次执行超时"
                elif status == "127":
                    status_text = "❌ 找不到命令"
                elif status == "running":
                    status_text = "🔄 可能仍在运行"
                elif status == "interrupted":
                    status_text = "⏹️ 上次被中断"
                elif status == "-1":
                    status_text = "⏹️ 上次用户中断"
                elif status == "-15":
                    status_text = "⏹️ 上次被终止"
                else:
                    status_text = f"⚠️ 上次退出码 {status}"
                self._task_log(f"状态: {status_text}", "info")
                # 更新状态栏
                self.task_status_label.config(text=f"状态: {status_text}")

            # 读取错误文件
            if error_file.exists():
                error_content = error_file.read_text(encoding="utf-8").strip()
                if error_content:
                    self._task_log("检测到错误输出:", "error")
                    self.task_log_text.insert(tk.END, error_content + "\n", "error")

            self._task_log(f"成功加载输出文件: {len(self.task_codex_messages)} 条消息", "success")

            # 记录当前文件位置以便继续监控
            self.task_output_position = len(content)

            # 询问是否启动监控
            if messagebox.askyesno("监控", "是否启动文件监控以查看新的输出？"):
                self._start_task_monitoring()

        except Exception as e:
            messagebox.showerror("错误", f"加载输出文件失败: {e}")
            self._task_log(f"加载失败: {e}", "error")

    def _clear_task_output(self):
        """清空输出文件和显示"""
        if not messagebox.askyesno("确认", "确定要清空所有输出文件和显示内容吗？"):
            return

        workspace_path = self.task_workspace_var.get()
        if workspace_path:
            output_file = Path(workspace_path) / "codex_output.txt"
            error_file = Path(workspace_path) / "codex_error.txt"
            status_file = Path(workspace_path) / "codex_status.txt"

            try:
                # 清空文件
                if output_file.exists():
                    output_file.write_text("", encoding="utf-8")
                if error_file.exists():
                    error_file.write_text("", encoding="utf-8")
                if status_file.exists():
                    status_file.write_text("", encoding="utf-8")

                self._task_log("输出文件已清空", "success")
            except Exception as e:
                self._task_log(f"清空文件失败: {e}", "error")

        # 清空显示
        self.task_codex_messages = []
        self.task_message_listbox.delete(0, tk.END)
        self.task_log_text.delete(1.0, tk.END)
        self.task_codex_positions = {}
        self.task_output_position = 0
        self.task_message_count_label.config(text="消息数: 0")

        self._task_log("显示内容已清空", "info")

    def _start_task_monitoring(self):
        """启动任务输出文件监控"""
        workspace_path = self.task_workspace_var.get()
        if not workspace_path:
            messagebox.showwarning("警告", "请先设置工作目录")
            return

        output_file = Path(workspace_path) / "codex_output.txt"
        error_file = Path(workspace_path) / "codex_error.txt"
        status_file = Path(workspace_path) / "codex_status.txt"

        # 如果还没有位置记录，获取当前文件大小
        if not hasattr(self, 'task_output_position'):
            self.task_output_position = output_file.stat().st_size if output_file.exists() else 0

        # 启动监控
        self.task_monitoring = True
        monitor_thread = threading.Thread(
            target=self._monitor_task_files,
            args=(output_file, error_file, status_file),
            daemon=True
        )
        monitor_thread.start()

        self._task_log("已启动文件监控", "success")

    def _stop_task_monitoring(self):
        """停止任务输出文件监控"""
        self.task_monitoring = False
        self._task_log("已停止文件监控", "info")

    def _ensure_api_key_for_executor(self):
        """确保API key被设置到环境变量中供执行器使用"""
        import os
        from pathlib import Path

        # 如果环境变量中已经有了，直接返回
        if os.environ.get("CODEX_API_KEY"):
            return

        # 尝试从GUI设置获取
        api_key = self.api_key_var.get().strip()

        # 尝试从缓存文件读取
        if not api_key:
            key_file = Path(".cache/codex_api_key")
            if key_file.exists():
                try:
                    api_key = key_file.read_text(encoding="utf-8").strip()
                except:
                    pass

        # 尝试从.env文件读取
        if not api_key:
            env_file = Path(".env")
            if env_file.exists():
                try:
                    with open(env_file, 'r') as f:
                        for line in f:
                            if line.startswith("CODEX_API_KEY="):
                                api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                                break
                except:
                    pass

        # 设置到环境变量
        if api_key:
            os.environ["CODEX_API_KEY"] = api_key
            self._task_log("✅ API key 已设置", "info")
        else:
            self._task_log("⚠️ 未找到 API key，请在'基本设置'中配置", "warning")


def main():
    root = tk.Tk()
    app = SboxgenGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app._save_settings(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
