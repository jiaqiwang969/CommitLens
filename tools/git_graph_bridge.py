#!/usr/bin/env python3
"""
Git Graph Data Bridge - 数据桥接方案
通过解析 git-graph 的输出，生成结构化数据供 GUI 使用
"""

import subprocess
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import hashlib

class GitGraphDataBridge:
    """Git Graph 数据桥接器 - 解析各种输出格式"""

    def __init__(self, git_graph_bin: str = None):
        self.git_graph_bin = git_graph_bin or self._find_git_graph()

    def _find_git_graph(self) -> str:
        """查找 git-graph 二进制"""
        import os
        import shutil

        # 检查项目内路径
        project_path = Path(__file__).parent.parent / "src/git-graph/target/release/git-graph"
        if project_path.exists():
            return str(project_path)

        # 检查系统 PATH
        sys_path = shutil.which("git-graph")
        if sys_path:
            return sys_path

        raise FileNotFoundError("git-graph not found")

    def get_graph_data(self, repo_path: Path, limit: int = 50) -> Dict:
        """获取图形数据

        返回格式：
        {
            "nodes": [{"id": str, "x": int, "y": int, "column": int, ...}],
            "edges": [{"from": int, "to": int, "color": str}],
            "branches": [{"name": str, "color": str}]
        }
        """
        # 1. 获取 ASCII 输出并解析列位置
        ascii_data = self._parse_ascii_output(repo_path, limit)

        # 2. 获取提交详细信息
        commit_details = self._get_commit_details(repo_path, limit)

        # 3. 获取父子关系
        parent_relations = self._get_parent_relations(repo_path, limit)

        # 4. 合并数据
        return self._merge_graph_data(ascii_data, commit_details, parent_relations)

    def _parse_ascii_output(self, repo_path: Path, limit: int) -> Dict:
        """解析 ASCII 输出获取列位置"""
        result = subprocess.run(
            [self.git_graph_bin, "--style", "ascii", "--no-color", "-n", str(limit)],
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        nodes = []
        for i, line in enumerate(result.stdout.splitlines()):
            # 查找 commit SHA
            sha_match = re.search(r'\b[0-9a-fA-F]{7}\b', line)
            if not sha_match:
                continue

            # 获取图形部分
            graph_part = line[:sha_match.start()]

            # 找到最右边的提交标记
            pos = -1
            for j in range(len(graph_part) - 1, -1, -1):
                if graph_part[j] in ('*', 'o', '●', '○'):
                    pos = j
                    break

            column = max(0, pos // 2)
            sha = sha_match.group(0).lower()

            # 提取分支信息
            branch_match = re.search(r'\(([^)]+)\)', line)
            branches = []
            if branch_match:
                branch_text = branch_match.group(1)
                # 解析分支名
                parts = branch_text.split(", ")
                for part in parts:
                    if "->" in part:  # HEAD -> main
                        branches.append(part.split(" -> ")[1])
                    else:
                        branches.append(part)

            nodes.append({
                "index": i,
                "short": sha,
                "column": column,
                "branches": branches,
                "is_merge": graph_part[pos] == 'o'
            })

        return {"nodes": nodes}

    def _get_commit_details(self, repo_path: Path, limit: int) -> List[Dict]:
        """获取提交详细信息"""
        result = subprocess.run(
            [
                "git", "log",
                "--format=%H%x01%P%x01%s%x01%an%x01%ae%x01%at%x01%b",
                f"-n{limit}"
            ],
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\x01")
            if len(parts) >= 6:
                commits.append({
                    "hash": parts[0],
                    "parents": parts[1].split() if parts[1] else [],
                    "subject": parts[2],
                    "author": parts[3],
                    "email": parts[4],
                    "timestamp": int(parts[5]) if parts[5] else 0,
                    "body": parts[6] if len(parts) > 6 else ""
                })

        return commits

    def _get_parent_relations(self, repo_path: Path, limit: int) -> Dict[str, List[str]]:
        """获取父子关系"""
        result = subprocess.run(
            ["git", "rev-list", "--parents", "--topo-order", f"-n{limit}", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True
        )

        relations = {}
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if parts:
                child = parts[0]
                parents = parts[1:] if len(parts) > 1 else []
                relations[child] = parents

        return relations

    def _merge_graph_data(self, ascii_data: Dict, commit_details: List[Dict],
                         parent_relations: Dict[str, List[str]]) -> Dict:
        """合并所有数据"""
        nodes = []
        edges = []

        # 创建 SHA 到索引的映射
        sha_to_index = {}
        for i, node in enumerate(ascii_data["nodes"]):
            if i < len(commit_details):
                commit = commit_details[i]
                full_sha = commit["hash"]
                sha_to_index[full_sha] = i

                # 合并节点信息
                nodes.append({
                    "index": i,
                    "id": full_sha,
                    "short": node["short"],
                    "column": node["column"],
                    "subject": commit["subject"],
                    "author": commit["author"],
                    "timestamp": commit["timestamp"],
                    "branches": node.get("branches", []),
                    "is_merge": node.get("is_merge", False),
                    "color": self._get_color_for_column(node["column"])
                })

        # 生成边
        for sha, parents in parent_relations.items():
            if sha in sha_to_index:
                from_idx = sha_to_index[sha]
                for parent in parents:
                    if parent in sha_to_index:
                        to_idx = sha_to_index[parent]
                        edges.append({
                            "from": from_idx,
                            "to": to_idx,
                            "color": nodes[from_idx]["color"]
                        })

        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "total_commits": len(nodes),
                "has_branches": any(n["column"] > 0 for n in nodes)
            }
        }

    def _get_color_for_column(self, column: int) -> str:
        """根据列号生成颜色"""
        colors = [
            "#1f77b4",  # 蓝色
            "#ff7f0e",  # 橙色
            "#2ca02c",  # 绿色
            "#d62728",  # 红色
            "#9467bd",  # 紫色
            "#8c564b",  # 棕色
            "#e377c2",  # 粉色
            "#7f7f7f",  # 灰色
        ]
        return colors[column % len(colors)]


class TkinterGraphRenderer:
    """使用 Tkinter Canvas 渲染图形"""

    def __init__(self, canvas):
        self.canvas = canvas
        self.node_items = []  # 存储节点图形项
        self.edge_items = []  # 存储边图形项
        self.hitboxes = []    # 存储点击区域

    def render(self, graph_data: Dict):
        """渲染图形数据到 Canvas"""
        # 清空画布
        self.canvas.delete("all")
        self.node_items.clear()
        self.edge_items.clear()
        self.hitboxes.clear()

        nodes = graph_data["nodes"]
        edges = graph_data["edges"]

        # 布局参数
        x_offset = 50
        y_offset = 30
        x_spacing = 30  # 列间距
        y_spacing = 25  # 行间距
        node_radius = 5

        # 计算节点位置
        node_positions = {}
        for node in nodes:
            x = x_offset + node["column"] * x_spacing
            y = y_offset + node["index"] * y_spacing
            node_positions[node["index"]] = (x, y)
            node["x"] = x
            node["y"] = y

        # 绘制边
        for edge in edges:
            if edge["from"] in node_positions and edge["to"] in node_positions:
                x1, y1 = node_positions[edge["from"]]
                x2, y2 = node_positions[edge["to"]]

                # 如果是跨列的边，绘制曲线
                if abs(x1 - x2) > x_spacing / 2:
                    # 绘制贝塞尔曲线
                    mid_y = (y1 + y2) / 2
                    line = self.canvas.create_line(
                        x1, y1, x1, mid_y, x2, mid_y, x2, y2,
                        fill=edge["color"],
                        smooth=True,
                        width=2
                    )
                else:
                    # 直线
                    line = self.canvas.create_line(
                        x1, y1, x2, y2,
                        fill=edge["color"],
                        width=2
                    )
                self.edge_items.append(line)

        # 绘制节点
        for node in nodes:
            x, y = node["x"], node["y"]

            # 绘制节点圆圈
            if node.get("is_merge"):
                # 合并提交用空心圆
                oval = self.canvas.create_oval(
                    x - node_radius, y - node_radius,
                    x + node_radius, y + node_radius,
                    fill="white",
                    outline=node["color"],
                    width=2
                )
            else:
                # 普通提交用实心圆
                oval = self.canvas.create_oval(
                    x - node_radius, y - node_radius,
                    x + node_radius, y + node_radius,
                    fill=node["color"],
                    outline=node["color"]
                )

            self.node_items.append(oval)

            # 创建点击区域
            hitbox = (
                x - node_radius - 5,
                y - node_radius - 5,
                x + node_radius + 5,
                y + node_radius + 5,
                node
            )
            self.hitboxes.append(hitbox)

        # 设置滚动区域
        max_x = max((n["x"] for n in nodes), default=100) + 100
        max_y = max((n["y"] for n in nodes), default=100) + 50
        self.canvas.configure(scrollregion=(0, 0, max_x, max_y))

    def get_node_at(self, x: float, y: float) -> Optional[Dict]:
        """获取指定坐标的节点"""
        for x1, y1, x2, y2, node in self.hitboxes:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return node
        return None


# 集成示例
def integrate_with_existing_gui(canvas, repo_path: Path):
    """集成到现有 GUI 的示例函数"""

    # 创建数据桥接器
    bridge = GitGraphDataBridge()

    # 获取图形数据
    graph_data = bridge.get_graph_data(repo_path, limit=50)

    # 创建渲染器
    renderer = TkinterGraphRenderer(canvas)

    # 渲染图形
    renderer.render(graph_data)

    # 绑定点击事件
    def on_click(event):
        x = canvas.canvasx(event.x)
        y = canvas.canvasy(event.y)
        node = renderer.get_node_at(x, y)
        if node:
            print(f"Clicked: {node['short']} - {node['subject']}")

    canvas.bind("<Button-1>", on_click)

    return renderer


if __name__ == "__main__":
    import tkinter as tk

    # 测试代码
    root = tk.Tk()
    root.title("Git Graph Data Bridge Demo")

    canvas = tk.Canvas(root, bg="#2a2a2a", width=800, height=600)
    canvas.pack(fill=tk.BOTH, expand=True)

    # 测试渲染
    repo = Path.cwd()
    if (repo / ".git").exists():
        bridge = GitGraphDataBridge()
        data = bridge.get_graph_data(repo, limit=30)

        # 打印数据结构
        print(f"Nodes: {len(data['nodes'])}")
        print(f"Edges: {len(data['edges'])}")
        print(f"Has branches: {data['metadata']['has_branches']}")

        # 渲染到画布
        renderer = TkinterGraphRenderer(canvas)
        renderer.render(data)

    root.mainloop()