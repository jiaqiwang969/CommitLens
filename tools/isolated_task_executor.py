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

        # 3. 复制对应的图片文件夹到 todolist/figs
        if task["figs"].exists():
            task_figs = todolist_dir / "figs"
            if task_figs.exists():
                shutil.rmtree(task_figs)
            shutil.copytree(task["figs"], task_figs)
            print(f"  ✓ 复制图片: {task['figs'].name}/ -> todolist/figs/")
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
        """提交任务结果"""
        print(f"\n💾 提交任务 {task['id']} 的结果...")

        try:
            # Git 操作
            subprocess.run(["git", "add", "-A"], cwd=str(self.current_dir), check=True)

            commit_msg = f"{task['id']}: 完成任务执行"
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=str(self.current_dir),
                check=True
            )

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
        """获取默认的prompt模板"""
        return f"""
请根据 {self.workspace_dir}/todolist/todolist-{task['id']}.tex 文档中描述的架构和需求，实现对应的 Rust 代码。

任务说明：
1. 仔细阅读 todolist/todolist-{task['id']}.tex 文档，理解其中描述的：
   - 系统架构设计
   - 模块划分和职责
   - 数据结构定义
   - 算法流程说明
   - 接口和API设计

2. 查看 todolist/figs/ 目录中的 PlantUML 图表（.puml 文件）：
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
   - 在 {self.workspace_dir}/{self.project_name} 目录中创建项目（固定目录名，便于迭代）
   - 创建合理的模块结构（lib.rs, mod.rs）
   - 实现 Cargo.toml 配置
   - 添加必要的依赖项
   - 确保代码可编译运行

输出要求：
- 生成完整可运行的 Rust 项目代码
- 包含单元测试和集成测试
- 提供简要的实现报告说明关键设计决策

注意：
- tex 文档位于：todolist/todolist-{task['id']}.tex
- 图表文件位于：todolist/figs/
- 项目代码应创建在：{self.project_name}/ （恒定目录名，支持多次迭代）
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
    print("3. 查看执行状态")
    print("4. 重置状态（慎用）")
    print("5. 退出")

    choice = input("\n请选择操作 (1-5): ")

    if choice == "1":
        executor.run_single_task()
    elif choice == "2":
        executor.run_all_tasks()
    elif choice == "3":
        executor.print_summary()
    elif choice == "4":
        executor.reset_status()
    elif choice == "5":
        print("👋 再见！")
    else:
        print("❌ 无效选择")


if __name__ == "__main__":
    main()