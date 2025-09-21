#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务隔离执行器 - 确保每个任务在完全独立的环境中执行
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime
import time

class IsolatedTaskExecutor:
    def __init__(self, workspace_dir=None, artifacts_dir=None, project_name=None):
        # 路径配置 - 支持自定义路径
        self.artifacts_dir = Path(artifacts_dir) if artifacts_dir else Path(".artifacts")
        self.workspace_dir = Path(workspace_dir) if workspace_dir else Path(".workspace")
        self.project_name = project_name if project_name else "rust-project"  # 默认项目名

        # 初始化所有相关路径
        self._update_paths()

    def _update_paths(self):
        """更新所有相关路径"""
        self.current_dir = self.workspace_dir / "current"
        self.status_file = self.workspace_dir / "task_status.json"
        self.log_dir = self.workspace_dir / "logs"

        # 确保工作目录存在
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 加载或初始化状态
        self.status = self.load_status()

        # 同步确保项目目录存在（用于提交结果）
        try:
            project_dir = self.workspace_dir / self.project_name
            project_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def set_workspace_dir(self, workspace_dir):
        """更新工作目录并重新初始化相关路径"""
        new_dir = Path(workspace_dir)
        # 只有当路径真正改变时才更新
        if new_dir != self.workspace_dir:
            self.workspace_dir = new_dir
            self._update_paths()

    def set_artifacts_dir(self, artifacts_dir):
        """更新产物目录"""
        self.artifacts_dir = Path(artifacts_dir)

    def set_project_name(self, project_name):
        """设置项目名称（固定输出目录名）"""
        self.project_name = project_name if project_name else "rust-project"

    def load_status(self):
        """加载任务执行状态"""
        if self.status_file.exists():
            return json.loads(self.status_file.read_text())
        else:
            return {
                "completed": [],
                "failed": {},
                "current": None,
                "last_execution": None
            }

    def save_status(self):
        """保存任务执行状态"""
        print(f"\n💾 保存状态到: {self.status_file}")
        print(f"  已完成: {self.status['completed']}")
        print(f"  已失败: {list(self.status['failed'].keys())}")
        self.status_file.write_text(json.dumps(self.status, indent=2))

    def get_all_tasks(self):
        """获取所有任务列表"""
        reports = sorted(self.artifacts_dir.glob("reports/*.tex"))
        tasks = []
        for report in reports:
            # 提取任务ID，如 001-84a2fb2
            task_id = report.stem
            tasks.append({
                "id": task_id,
                "report": report,
                "figs": self.artifacts_dir / "figs" / task_id
            })
        return tasks

    def get_next_task(self):
        """获取下一个未完成的任务"""
        all_tasks = self.get_all_tasks()
        print(f"\n🔍 检查任务状态...")
        print(f"  已完成: {self.status['completed']}")
        print(f"  已失败: {list(self.status['failed'].keys())}")

        for task in all_tasks:
            if task["id"] not in self.status["completed"]:
                # 检查是否失败次数过多
                fail_count = self.status["failed"].get(task["id"], 0)
                if fail_count >= 3:
                    print(f"  ⚠️ 任务 {task['id']} 失败{fail_count}次，跳过")
                    continue
                print(f"  ➡️ 下一个任务: {task['id']} (失败{fail_count}次)")
                return task

        print(f"  ✅ 所有任务已完成")
        return None

    def prepare_workspace(self, task):
        """准备隔离的工作空间"""
        print(f"\n📦 准备任务 {task['id']} 的隔离环境...")
        print(f"  📁 工作空间根目录: {self.workspace_dir}")

        # 创建 todolist 子目录结构
        todolist_dir = self.workspace_dir / "todolist"
        todolist_dir.mkdir(parents=True, exist_ok=True)
        print(f"  📂 创建任务目录: {todolist_dir.relative_to(self.workspace_dir)}/")

        # 1. 清理旧的 todolist 内容
        for old_file in todolist_dir.glob("*"):
            if old_file.is_file():
                old_file.unlink()
            elif old_file.is_dir():
                shutil.rmtree(old_file)

        # 2. 复制任务文件到 todolist 目录，重命名为 todolist-{task_id}.tex
        task_report = todolist_dir / f"todolist-{task['id']}.tex"
        shutil.copy2(task["report"], task_report)
        print(f"  ✓ 复制报告: {task['report'].name} -> todolist/todolist-{task['id']}.tex")

        # 3. 复制对应的图片文件夹到 todolist/figs（仅保留 .puml，排除 .svg/.pdf 等）
        if task["figs"].exists():
            src_figs = task["figs"]
            task_figs = todolist_dir / "figs"
            if task_figs.exists():
                shutil.rmtree(task_figs)
            task_figs.mkdir(parents=True, exist_ok=True)

            copied = 0
            try:
                for path in src_figs.rglob("*"):
                    if path.is_dir():
                        continue
                    if path.suffix.lower() != ".puml":
                        # skip non-puml (e.g., .svg/.pdf)
                        continue
                    rel = path.relative_to(src_figs)
                    dst = task_figs / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dst)
                    copied += 1
            except Exception as e:
                print(f"  ⚠️ 复制 puml 文件时出错: {e}")

            print(f"  ✓ 复制图片(puml-only): {src_figs.name}/ -> todolist/figs/ ({copied} files; svg/pdf excluded)")
        else:
            print(f"  ℹ️ 未找到图片目录: {task['figs']}")

        # 4. 创建任务元信息
        meta_file = todolist_dir / "task_meta.json"
        meta_file.write_text(json.dumps({
            "task_id": task["id"],
            "start_time": datetime.now().isoformat(),
            "source_report": str(task["report"]),
            "source_figs": str(task["figs"]),
            "workspace_dir": str(self.workspace_dir),
            "todolist_dir": str(todolist_dir),
            "project_name": self.project_name,
            "project_output_dir": str(self.workspace_dir / self.project_name)
        }, indent=2))

        # 5. 确保项目输出目录存在并初始化 Git 仓库（如有必要）
        project_dir = self.workspace_dir / self.project_name
        project_dir.mkdir(parents=True, exist_ok=True)
        try:
            # 若未初始化为 git 仓库，则执行 git init（幂等）
            if not (project_dir / ".git").exists():
                subprocess.run(["git", "init"], cwd=str(project_dir), check=True)
                print(f"  ✓ 已初始化 Git 仓库: {project_dir}")
        except Exception as e:
            print(f"  ⚠️ Git 初始化失败（忽略继续）: {e}")

        print(f"\n  📋 目录结构:")
        print(f"  {self.workspace_dir.name}/")
        print(f"  ├── todolist/")
        print(f"  │   ├── todolist-{task['id']}.tex")
        if task["figs"].exists():
            print(f"  │   └── figs/")
        print(f"  └── {self.project_name}/ (项目输出目录，恒定名称)")

        print(f"\n  ✓ 工作空间准备完成")
        print(f"  ✓ Codex 将在工作空间根目录执行: {self.workspace_dir}")
        print(f"  ✓ 项目将输出到: {self.workspace_dir / self.project_name}")
        return True

    def execute_task(self, task, custom_prompt=None):
        """在隔离环境中执行任务"""
        print(f"\n🚀 执行任务 {task['id']}...")

        # 如果提供了自定义 prompt，使用变量替换
        if custom_prompt:
            prompt = self._substitute_prompt_variables(custom_prompt, task)
        else:
            # 默认 prompt 模板
            prompt = self._get_default_prompt(task)

        # 添加任务ID
        prompt += f"\n\n任务ID: {task['id']}"

        # 记录日志
        log_file = self.log_dir / f"{task['id']}.log"

        try:
            # 准备环境变量，确保包含 API key
            env = os.environ.copy()

            # 尝试从多个来源获取 API key
            api_key = None

            # 1. 从环境变量获取
            if "CODEX_API_KEY" in env:
                api_key = env["CODEX_API_KEY"]

            # 2. 从 .cache/codex_api_key 文件获取
            if not api_key:
                key_file = Path(".cache/codex_api_key")
                if key_file.exists():
                    try:
                        api_key = key_file.read_text(encoding="utf-8").strip()
                    except:
                        pass

            # 3. 从 .env 文件获取
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

            if api_key:
                env["CODEX_API_KEY"] = api_key
            else:
                print("  ⚠️ 警告: 未找到 CODEX_API_KEY")
                print("  请通过以下方式之一设置:")
                print("  1) export CODEX_API_KEY='your-key'")
                print("  2) echo 'your-key' > .cache/codex_api_key")
                print("  3) 在 .env 文件中添加 CODEX_API_KEY=your-key")

            # 执行 codex 命令
            cmd = [
                "codex", "exec",
                "--skip-git-repo-check",
                "--sandbox", "workspace-write",
                prompt
            ]

            # 在工作空间根目录中执行（而不是 current 子目录）
            result = subprocess.run(
                cmd,
                cwd=str(self.workspace_dir),  # 改为在工作空间根目录执行
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                env=env  # 使用包含 API key 的环境变量
            )

            # 保存执行日志
            with open(log_file, 'w') as f:
                f.write(f"=== 任务 {task['id']} 执行日志 ===\n")
                f.write(f"时间: {datetime.now()}\n")
                f.write(f"命令: {' '.join(cmd)}\n")
                f.write(f"返回码: {result.returncode}\n")
                f.write(f"\n--- 标准输出 ---\n{result.stdout}\n")
                f.write(f"\n--- 标准错误 ---\n{result.stderr}\n")

            if result.returncode == 0:
                print(f"  ✓ 任务执行成功")
                return True
            else:
                print(f"  ✗ 任务执行失败，返回码: {result.returncode}")
                return False

        except subprocess.TimeoutExpired:
            print(f"  ✗ 任务执行超时")
            return False
        except Exception as e:
            print(f"  ✗ 任务执行异常: {e}")
            return False

    def commit_results(self, task):
        """在 {project_name} 目录内提交任务结果。

        - 使用全角冒号的提交信息格式："{task_id}：xxxxx。"
        - 仅在项目目录内执行 git 操作，避免污染工作空间其它文件。
        """
        print(f"\n💾 提交任务 {task['id']} 的结果...")

        project_dir = self.workspace_dir / self.project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 若未初始化为 git 仓库，则执行 git init（幂等）
            if not (project_dir / ".git").exists():
                subprocess.run(["git", "init"], cwd=str(project_dir), check=True)
                print(f"  ✓ 已初始化 Git 仓库: {project_dir}")

            # Git 操作（限定在项目目录）
            subprocess.run(["git", "add", "-A"], cwd=str(project_dir), check=True)

            commit_msg = f"{task['id']}：完成任务执行。"
            subprocess.run([
                "git", "commit", "-m", commit_msg
            ], cwd=str(project_dir), check=True)

            print(f"  ✓ 已提交: {commit_msg}")
            return True

        except subprocess.CalledProcessError as e:
            print(f"  ✗ 提交失败: {e}")
            return False

    def cleanup_workspace(self):
        """清理工作空间"""
        print(f"\n🧹 清理工作空间...")

        # 保存必要的结果（如果需要）
        # ...

        # 清理 todolist 目录内容（但保留目录本身）
        todolist_dir = self.workspace_dir / "todolist"
        if todolist_dir.exists():
            for item in todolist_dir.glob("*"):
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            print(f"  ✓ 已清理: {todolist_dir}/")

    # === 新增：从指定 commit（任务ID）开始重新执行 ===
    def _git(self, args, cwd: Path, check=True, capture_output=True):
        """Run a git command under cwd and return CompletedProcess."""
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=check,
            capture_output=capture_output,
            text=True,
        )

    def _project_dir(self) -> Path:
        return self.workspace_dir / self.project_name

    def _ensure_project_repo(self) -> bool:
        p = self._project_dir()
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
        # init if missing
        try:
            if not (p / ".git").exists():
                self._git(["init"], cwd=p)
        except Exception:
            return False
        return True

    def _git_current_branch(self) -> Optional[str]:
        p = self._project_dir()
        try:
            cp = self._git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=p)
            name = (cp.stdout or "").strip()
            return name if name and name != "HEAD" else name
        except Exception:
            return None

    def _git_is_clean(self) -> bool:
        p = self._project_dir()
        try:
            cp = self._git(["status", "--porcelain"], cwd=p)
            return (cp.stdout or "").strip() == ""
        except Exception:
            return False

    def _find_commit_by_task_id(self, task_id: str) -> Optional[str]:
        p = self._project_dir()
        # 支持纯数字（如 1/01/001）：按三位序号前缀匹配（^001-）
        norm_prefix: Optional[str] = None
        t = (task_id or "").strip()
        if t.isdigit():
            z3 = f"{int(t):03d}"
            norm_prefix = f"^{z3}-"
        elif "-" not in t and len(t) == 3 and all(ch.isdigit() for ch in t):
            norm_prefix = f"^{t}-"

        # 优先匹配完整 ID（NNN-xxxxxxx）带中文/英文冒号的样式
        patterns = [f"^{t}：", f"^{t}:"]
        # 其次匹配仅有序号的前缀形式（^NNN-）
        if norm_prefix:
            patterns.insert(0, norm_prefix)
        for pat in patterns:
            try:
                cp = self._git(["log", "--all", "-n", "1", f"--grep={pat}", "--format=%H"], cwd=p)
                sha = (cp.stdout or "").strip()
                if sha:
                    return sha
            except Exception:
                pass
        # 兜底：扫描最近 1000 条提交，在 subject 中查找 task_id
        try:
            cp = self._git(["log", "-n", "1000", "--pretty=%H;%s"], cwd=p)
            for line in (cp.stdout or "").splitlines():
                try:
                    sha, subj = line.split(";", 1)
                except ValueError:
                    continue
                # 完整 ID（NNN-xxxxxxx）样式
                if subj.startswith(f"{t}：") or subj.startswith(f"{t}:"):
                    return sha
                # 仅序号形式：^NNN-
                if norm_prefix and subj.startswith(norm_prefix[1:]):
                    return sha
        except Exception:
            pass
        return None

    def _update_status_up_to(self, task_id: str) -> None:
        # 将 task_status.json 的 completed 置为从 .artifacts/reports 中按序到 task_id（含）为止。
        all_reports = sorted(self.artifacts_dir.glob("reports/*.tex"))
        ids = [p.stem for p in all_reports]
        try:
            idx = ids.index(task_id)
        except ValueError:
            print(f"⚠️ 未在 .artifacts/reports/ 中找到 {task_id}.tex，保持原状态")
            return
        # 以该 id 为起点，执行“下一个 commit”，所以将该 id 标为已完成
        completed = ids[: idx + 1]
        self.status["completed"] = completed
        self.status["failed"] = {}
        self.status["current"] = None
        self.status["last_execution"] = datetime.now().isoformat()
        self.save_status()

    def rerun_from_commit(self, start_task_id: str, delay_between_tasks: int = 5, run: bool = True) -> bool:
        # 从项目仓库中定位以“{start_task_id}：”提交消息的提交，基于该提交创建新分支；
        # 将当前主分支重命名为“历史分支-<timestamp>”，并把新分支改名为原主分支名；
        # 随后更新执行状态，使 {start_task_id} 之前的任务视为已完成，从下一个任务开始重新执行所有任务。
        print("\n🧭 准备从指定 commit 重新执行所有任务…")
        print(f"  ⏱️ 起点任务ID: {start_task_id}")

        if not self._ensure_project_repo():
            print("❌ 未能初始化/定位项目 Git 仓库")
            return False
        project_dir = self._project_dir()

        # 安全检查：工作区需干净
        if not self._git_is_clean():
            print("❌ 项目仓库存在未提交更改，请先提交或清理后重试")
            return False

        # 查找对应 commit
        sha = self._find_commit_by_task_id(start_task_id)
        if not sha:
            print("❌ 未找到对应的提交（按提交消息前缀匹配）。请确认任务ID正确，例如 021-b4b7821。")
            return False
        print(f"  🔎 找到提交: {sha}")

        # 当前主分支名
        curr = self._git_current_branch() or "main"
        print(f"  🌿 当前分支: {curr}")

        # 生成时间戳
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        replay_branch = f"replay-{ts}"
        history_branch = f"历史分支-{ts}"

        try:
            # 1) 从目标提交创建并切换到临时重放分支
            self._git(["checkout", "-b", replay_branch, sha], cwd=project_dir)
            print(f"  ✓ 已创建并切换到分支: {replay_branch} @ {sha}")

            # 2) 将原来的主分支改名为 历史分支-<ts>
            #    注意：此时不在原分支上，可以直接改名
            self._git(["branch", "-m", curr, history_branch], cwd=project_dir)
            print(f"  ✓ 已重命名原分支 {curr} -> {history_branch}")

            # 3) 将当前分支（replay-<ts>）改回原主分支名，使之成为新的主分支
            self._git(["branch", "-m", curr], cwd=project_dir)
            print(f"  ✓ 将 {replay_branch} 改名为新的主分支 {curr}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Git 分支操作失败: {e}")
            return False

        # 更新状态：把起点 id 标记为已完成，从下一条开始执行
        self._update_status_up_to(start_task_id)

        if run:
            # 连续执行所有剩余任务
            print("\n🔁 开始从下一条任务起重新执行所有任务…")
            self.run_all_tasks(delay_between_tasks=delay_between_tasks)
        return True

    def _substitute_prompt_variables(self, prompt, task):
        """替换prompt中的变量"""
        variables = {
            "{workspace_dir}": str(self.workspace_dir),
            "{todolist_dir}": str(self.workspace_dir / "todolist"),
            "{project_dir}": str(self.workspace_dir / self.project_name),  # 使用固定项目名
            "{project_name}": self.project_name,  # 项目名称变量
            "{task_id}": task['id'],
            "{tex_file}": f"todolist/todolist-{task['id']}.tex",
            "{figs_dir}": "todolist/figs"
        }

        result = prompt
        substituted = []
        for var, value in variables.items():
            if var in prompt:
                result = result.replace(var, value)
                substituted.append(f"    {var} → {value}")

        # 记录变量替换
        if substituted:
            print(f"\n  📝 变量替换:")
            for sub in substituted:
                print(sub)
        else:
            print(f"\n  ℹ️ 无需变量替换（未发现变量标记）")

        return result

    def _get_default_prompt(self, task):
        """获取默认的 prompt：复现 commit 报告代码内容（含环境与提交约定）"""
        return f"""
请在 {self.workspace_dir} 内，依据 todolist/todolist-{task['id']}.tex 的提交报告，忠实复现该提交（以 HEAD 为准）的代码内容，并将结果写入固定目录 {self.workspace_dir}/{self.project_name}。

提示：当前已在 {self.workspace_dir}（通常为 .workspace）。可先执行 `ls -la` 查看顶层目录，确认存在 todolist/ 与 {self.project_name}/。

一、信息收集
- 打开 tex 报告；如有，参考 todolist/figs/{task['id']}/ 下的图示（类图/序列图/流程图/状态图）
- 提取报告中出现的文件路径、模块/类名、代码片段、配置与命令；识别应新增/修改/删除的文件集合

二、代码复现
- 在 {self.workspace_dir}/{self.project_name} 内按报告还原最终文件内容：逐项创建/修改/删除文件；代码以报告中的完整片段为准
- 若片段缺失或上下文不全，填充最小可行的占位内容，并以 TODO 标注依据与缺失
- 若报告包含非 Rust 片段且已明确语言/框架，则按原语言复现；否则以 Rust 项目做最小演示，并将非 Rust 片段以资源/注释方式保存

三、构建校验
- 优先使用报告中给出的构建/运行命令；否则（若为 Rust 项目）执行 cargo build/test，并补齐必要样例

四、提交
- 在 {self.workspace_dir}/{self.project_name} 中 `git add -A` 并提交，提交信息格式："{task['id']}：复现提交代码内容。"

五、复现说明
- 输出简要说明：列出复现的文件、依据的片段或图示、关键假设/妥协与验证结果

注意
- 目标是“复现报告中的代码状态”，避免超出报告范围的重构或新增设计

限制（禁止修改）
- 禁止修改以下路径/文件（它们由系统管理）：
  - {self.workspace_dir}/codex_error.txt
  - {self.workspace_dir}/codex_status.txt
  - {self.workspace_dir}/codex_output.txt
  - {self.workspace_dir}/logs/
  - {self.workspace_dir}/task_status.json
  - {self.workspace_dir}/todolist/
- 仅允许在 {self.workspace_dir}/{self.project_name}/ 目录内创建/修改/删除代码与配置。
"""

    def run_single_task(self):
        """执行单个任务的完整流程"""
        # 1. 获取下一个任务
        task = self.get_next_task()
        if not task:
            print("✅ 所有任务已完成！")
            return False

        print(f"\n{'='*60}")
        print(f"📋 开始处理任务: {task['id']}")
        print(f"{'='*60}")

        # 2. 更新状态
        self.status["current"] = task["id"]
        self.save_status()

        try:
            # 3. 准备隔离环境
            if not self.prepare_workspace(task):
                raise Exception("工作空间准备失败")

            # 4. 执行任务
            success = self.execute_task(task)

            if success:
                # 5. 提交结果
                if self.commit_results(task):
                    # 6. 标记完成
                    self.status["completed"].append(task["id"])
                    print(f"✅ 任务 {task['id']} 完成")
                else:
                    raise Exception("提交失败")
            else:
                raise Exception("执行失败")

        except Exception as e:
            # 记录失败
            print(f"❌ 任务 {task['id']} 失败: {e}")
            self.status["failed"][task["id"]] = self.status["failed"].get(task["id"], 0) + 1

        finally:
            # 7. 清理环境（无论成功失败都要清理）
            self.cleanup_workspace()

            # 8. 更新状态
            self.status["current"] = None
            self.status["last_execution"] = datetime.now().isoformat()
            self.save_status()

        return True  # 还有任务可以继续

    def run_all_tasks(self, delay_between_tasks=5):
        """连续执行所有任务"""
        print("🔄 开始批量执行任务...")

        task_count = 0
        while self.run_single_task():
            task_count += 1
            print(f"\n⏰ 等待 {delay_between_tasks} 秒后执行下一个任务...")
            time.sleep(delay_between_tasks)

        print(f"\n✨ 批量执行完成！共处理 {task_count} 个任务")
        self.print_summary()

    def print_summary(self):
        """打印执行摘要"""
        print("\n" + "="*60)
        print("📊 执行摘要")
        print("="*60)
        print(f"✅ 已完成: {len(self.status['completed'])} 个任务")
        if self.status['completed']:
            for task_id in self.status['completed'][-5:]:  # 显示最后5个
                print(f"    - {task_id}")

        print(f"❌ 失败: {len(self.status['failed'])} 个任务")
        if self.status['failed']:
            for task_id, count in self.status['failed'].items():
                print(f"    - {task_id} (失败 {count} 次)")

    def reset_status(self):
        """重置执行状态（慎用）"""
        confirm = input("⚠️ 确定要重置所有执行状态吗？(yes/no): ")
        if confirm.lower() == "yes":
            self.status = {
                "completed": [],
                "failed": {},
                "current": None,
                "last_execution": None
            }
            self.save_status()
            print("✓ 状态已重置")


def main():
    """主程序入口"""
    executor = IsolatedTaskExecutor()

    print("🎯 任务隔离执行器")
    print("1. 执行单个任务")
    print("2. 批量执行所有任务")
    print("3. 从指定 commit 开始重新执行所有任务（自动创建新分支并切换为主分支）")
    print("4. 查看执行状态")
    print("5. 重置状态（慎用）")
    print("6. 退出")

    choice = input("\n请选择操作 (1-6): ")

    if choice == "1":
        executor.run_single_task()
    elif choice == "2":
        executor.run_all_tasks()
    elif choice == "3":
        start_id = input("请输入起始 commit 任务ID（例如 021-b4b7821）: ").strip()
        if not start_id:
            print("❌ 任务ID不能为空")
        else:
            executor.rerun_from_commit(start_id)
    elif choice == "4":
        executor.print_summary()
    elif choice == "5":
        executor.reset_status()
    elif choice == "6":
        print("👋 再见！")
    else:
        print("❌ 无效选择")


if __name__ == "__main__":
    main()
