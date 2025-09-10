#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import shlex
import signal
import threading
import subprocess
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import queue
from typing import Optional


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
        self.timeline_root_var = tk.StringVar(value=str(Path(".sboxes_timeline")))
        self.timeline_tex_root_var = tk.StringVar(value=str(Path(".sboxes_timeline_tex")))
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

        # 输出目录衍生/覆盖跟踪
        self._out_overridden = False
        try:
            self._last_derived_out = str((Path(f".sboxes_{self.style_var.get()}")).resolve())
        except Exception:
            self._last_derived_out = str(Path(".sboxes_timeline").resolve())

        # step status: pending → running → ok/fail
        self.steps = [
            {"key": "mirror", "label": "1) 镜像仓库 mirror", "status": tk.StringVar(value="pending")},
            {"key": "gen", "label": "2) 生成时间线 gen", "status": tk.StringVar(value="pending")},
            {"key": "verify", "label": "3) 校验生成 verify", "status": tk.StringVar(value="pending")},
            {"key": "codex", "label": "4) 批量 Codex 执行", "status": tk.StringVar(value="pending")},
            {"key": "collect_tex", "label": "5) 收集为 .sboxes_timeline_tex", "status": tk.StringVar(value="pending")},
            {"key": "texfix", "label": "6) 并行 PUML+LaTeX 修复（按提交）", "status": tk.StringVar(value="pending")},
            {"key": "fixbug", "label": "7) 汇总并生成 PDF", "status": tk.StringVar(value="pending")},
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
        nb.add(tab_basic, text="基本设置")
        nb.add(tab_codex, text="Codex 与参数")
        nb.add(tab_readme, text="README 模板")
        nb.add(tab_run, text="执行与日志")

        # --- basic tab ---
        for i in range(8):
            tab_basic.rowconfigure(i, weight=0)
        tab_basic.columnconfigure(1, weight=1)

        ttk.Label(tab_basic, text="Git 仓库 URL:").grid(row=0, column=0, sticky="w", pady=6)
        e_repo = ttk.Entry(tab_basic, textvariable=self.repo_var)
        e_repo.grid(row=0, column=1, sticky="ew", padx=(8, 8), pady=6)
        ttk.Button(tab_basic, text="推断镜像路径", command=self._autofill_mirror).grid(row=0, column=2, pady=6)

        ttk.Label(tab_basic, text="分支:").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Combobox(tab_basic, values=["master", "main"], textvariable=self.branch_var, state="readonly")\
            .grid(row=1, column=1, sticky="w", padx=(8, 8), pady=6)

        ttk.Label(tab_basic, text="提交数 limit:").grid(row=1, column=2, sticky="e")
        ttk.Spinbox(tab_basic, from_=1, to=200, textvariable=self.limit_var, width=8).grid(row=1, column=3, sticky="w", padx=(8, 0))

        ttk.Label(tab_basic, text="风格 (模板):").grid(row=2, column=0, sticky="w", pady=6)
        self.style_combo = ttk.Combobox(tab_basic, values=[], textvariable=self.style_var, state="readonly")
        self.style_combo.grid(row=2, column=1, sticky="w", padx=(8, 8), pady=6)

        ttk.Label(tab_basic, text="镜像路径 mirror:").grid(row=3, column=0, sticky="w", pady=6)
        e_mirror = ttk.Entry(tab_basic, textvariable=self.mirror_var)
        e_mirror.grid(row=3, column=1, sticky="ew", padx=(8, 8), pady=6)
        ttk.Button(tab_basic, text="浏览", command=self._browse_mirror).grid(row=3, column=2, pady=6)

        ttk.Label(tab_basic, text="时间线根目录 out:").grid(row=4, column=0, sticky="w", pady=6)
        e_out = ttk.Entry(tab_basic, textvariable=self.timeline_root_var)
        e_out.grid(row=4, column=1, sticky="ew", padx=(8, 8), pady=6)
        ttk.Button(tab_basic, text="浏览", command=self._browse_out).grid(row=4, column=2, pady=6)
        e_out.bind('<KeyRelease>', lambda e: setattr(self, '_out_overridden', True))

        ttk.Label(tab_basic, text="TEX 时间线根目录 (收集输出):").grid(row=5, column=0, sticky="w", pady=6)
        e_out_tex = ttk.Entry(tab_basic, textvariable=self.timeline_tex_root_var)
        e_out_tex.grid(row=5, column=1, sticky="ew", padx=(8, 8), pady=6)
        ttk.Button(tab_basic, text="浏览", command=self._browse_out_tex).grid(row=5, column=2, pady=6)

        ttk.Label(tab_basic, text="产物目录 artifacts:").grid(row=6, column=0, sticky="w", pady=6)
        e_art = ttk.Entry(tab_basic, textvariable=self.artifacts_root_var)
        e_art.grid(row=6, column=1, sticky="ew", padx=(8, 8), pady=6)
        ttk.Button(tab_basic, text="浏览", command=self._browse_artifacts).grid(row=6, column=2, pady=6)

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

    def _bind_events(self):
        self.repo_var.trace_add("write", lambda *_: self._maybe_update_mirror())
        self.style_var.trace_add("write", lambda *_: self._on_style_change())

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
                self.timeline_root_var.set(data.get("timeline_root", self.timeline_root_var.get()))
                self.timeline_tex_root_var.set(data.get("timeline_tex_root", self.timeline_tex_root_var.get()))
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
                "timeline_root": self.timeline_root_var.get(),
                "timeline_tex_root": self.timeline_tex_root_var.get(),
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
            }
            self.settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---------------- helpers ----------------
    def _autofill_mirror(self):
        self.mirror_var.set(_default_mirror_from_repo(self.repo_var.get()))

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
            self.timeline_root_var.set(path)
            # optional: could rescan dirs if needed for template derivation
            self._out_overridden = True
            try:
                self._refresh_chain_total()
            except Exception:
                pass

    def _browse_out_tex(self):
        path = filedialog.askdirectory(title="选择 TEX 时间线根目录")
        if path:
            self.timeline_tex_root_var.set(path)

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
        out_root = self.timeline_root_var.get().strip()
        out_tex_root = self.timeline_tex_root_var.get().strip()
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
                # 生成结构固定 timeline；风格仅决定 README 模板与输出目录
                "gen", "--mirror", mirror, "--branch", branch, "--out", out_root,
                "--limit", str(limit), "--overwrite", "--style", "timeline"
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
            # Step 6: parallel PUML+LaTeX fix inside .sboxes_timeline_tex
            args = [
                "tex-fix", "--root", out_tex_root, "--limit", str(limit),
                "--timeout", str(timeout), "--max-parallel", str(int(self.max_parallel_var.get() or 0) or 1),
                "--runs", str(int(self.puml_runs_var.get() or 1))
            ]
            if self.puml_force_var.get():
                args.append("--force")
            cmd = self._python_cmd(*args)
        elif key == "fixbug":
            # Step 7: collect from .sboxes_timeline_tex into .artifacts, then fix main.tex
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
        except queue.Empty:
            pass

        self.root.after(100, self._drain_queues)

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
            timeline = Path(self.timeline_root_var.get()).resolve()
            to_backup = [p for p in [artifacts, timeline] if p.exists()]

            if not to_backup:
                self._append_log("未发现可备份的目录（.artifacts 或 .sboxes_timeline）。")
                messagebox.showinfo("无可备份内容", "未发现 .artifacts 或 .sboxes_timeline。")
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
            new_default = str((Path(f".sboxes_{self._sanitize_style_name(self.style_var.get())}")).resolve())
        except Exception:
            new_default = str(Path(".sboxes_timeline").resolve())
        cur = str(Path(self.timeline_root_var.get()).resolve()) if self.timeline_root_var.get() else ""
        # Update if user hasn't overridden or if current equals last derived
        if not self._out_overridden or cur == self._last_derived_out or cur == "":
            try:
                # set without marking overridden
                self.timeline_root_var.set(str(Path(new_default)))
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
            root = Path(self.timeline_root_var.get()).resolve()
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
            "请进入到‘{dir}’，优先完成图形修复与导出，然后进行 LaTeX 编译：\n"
            "一、PlantUML 修复与导出：\n"
            "1) 在 figs 子目录中查找 algorithm_flow.puml（若存在）；\n"
            "2) 执行：plantuml -tsvg algorithm_flow.puml 生成 SVG；\n"
            "3) 若出现如 ‘Error line N in file ...’ 的错误，请打开并修复（语法、引号、未闭合括号、缺少 @startuml/@enduml 等）；\n"
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


def main():
    root = tk.Tk()
    app = SboxgenGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app._save_settings(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
