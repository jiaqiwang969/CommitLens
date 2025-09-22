#!/usr/bin/env python3
"""
Git Graph Integration Module for Python GUI
集成 git-graph 到 Python GUI 的改进方案
"""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import tkinter as tk
from PIL import Image, ImageTk
import tempfile
import json
import re

class GitGraphRenderer:
    """Git Graph 渲染器 - 支持多种渲染方式"""

    def __init__(self, git_graph_bin: str = None):
        """初始化渲染器

        Args:
            git_graph_bin: git-graph 二进制路径
        """
        self.git_graph_bin = git_graph_bin or self._find_git_graph()
        self.commit_nodes = []  # 存储节点信息
        self.svg_data = None
        self.png_image = None

    def _find_git_graph(self) -> str:
        """查找 git-graph 二进制文件"""
        # 优先级：环境变量 -> 项目内 -> 系统 PATH
        import os
        import shutil

        # 1. 环境变量
        env_path = os.environ.get("GIT_GRAPH_BIN")
        if env_path and Path(env_path).exists():
            return env_path

        # 2. 项目内编译版本
        project_paths = [
            Path(__file__).parent.parent / "src/git-graph/target/release/git-graph",
            Path(__file__).parent.parent / "vendor/git-graph/bin/git-graph",
        ]
        for p in project_paths:
            if p.exists():
                return str(p)

        # 3. 系统 PATH
        sys_path = shutil.which("git-graph")
        if sys_path:
            return sys_path

        raise FileNotFoundError("git-graph binary not found")

    def render_svg(self, repo_path: Path, num_commits: int = 50) -> str:
        """生成 SVG 图形

        Args:
            repo_path: 仓库路径
            num_commits: 显示的提交数量

        Returns:
            SVG 内容字符串
        """
        result = subprocess.run(
            [self.git_graph_bin, "--svg", "-n", str(num_commits)],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True
        )
        self.svg_data = result.stdout
        return self.svg_data

    def parse_svg_nodes(self, svg_content: str) -> List[Dict]:
        """解析 SVG 获取节点坐标

        Args:
            svg_content: SVG 内容

        Returns:
            节点信息列表 [{x, y, commit_index}, ...]
        """
        root = ET.fromstring(svg_content)
        nodes = []

        # 查找所有圆形节点（提交）
        for circle in root.findall(".//{http://www.w3.org/2000/svg}circle"):
            cx = float(circle.get("cx", 0))
            cy = float(circle.get("cy", 0))
            # 根据 y 坐标推算提交索引（假设每个提交间隔15像素）
            commit_index = int((cy - 15) / 15)
            nodes.append({
                "x": cx,
                "y": cy,
                "index": commit_index,
                "radius": float(circle.get("r", 4))
            })

        self.commit_nodes = nodes
        return nodes

    def svg_to_png(self, svg_path: Path, png_path: Path):
        """将 SVG 转换为 PNG（使用系统工具）"""
        import sys

        if sys.platform == "darwin":
            # macOS 使用 sips
            subprocess.run(
                ["sips", "-s", "format", "png", str(svg_path), "--out", str(png_path)],
                check=True
            )
        else:
            # Linux/Windows 使用 rsvg-convert 或 inkscape
            try:
                subprocess.run(
                    ["rsvg-convert", "-f", "png", "-o", str(png_path), str(svg_path)],
                    check=True
                )
            except FileNotFoundError:
                subprocess.run(
                    ["inkscape", str(svg_path), "-o", str(png_path)],
                    check=True
                )

class InteractiveGraphCanvas(tk.Frame):
    """交互式图形画布 - 结合 SVG 渲染和 Canvas 交互"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.renderer = GitGraphRenderer()
        self.canvas = None
        self.commit_mapping = {}  # 坐标到提交的映射
        self.setup_ui()

    def setup_ui(self):
        """设置 UI 组件"""
        # 创建 Canvas
        self.canvas = tk.Canvas(self, bg="#2a2a2a")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 滚动条
        v_scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar = tk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.canvas.xview)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.configure(
            yscrollcommand=v_scrollbar.set,
            xscrollcommand=h_scrollbar.set
        )

        # 绑定事件
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_motion)

    def render_graph(self, repo_path: Path, num_commits: int = 50):
        """渲染图形

        Args:
            repo_path: 仓库路径
            num_commits: 显示的提交数
        """
        # 1. 生成 SVG
        svg_content = self.renderer.render_svg(repo_path, num_commits)

        # 2. 解析节点坐标
        nodes = self.renderer.parse_svg_nodes(svg_content)

        # 3. 转换为 PNG 并显示
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as svg_file:
            svg_file.write(svg_content.encode())
            svg_path = Path(svg_file.name)

        png_path = svg_path.with_suffix(".png")
        self.renderer.svg_to_png(svg_path, png_path)

        # 4. 加载 PNG 到 Canvas
        img = Image.open(png_path)
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

        # 5. 设置滚动区域
        self.canvas.configure(scrollregion=(0, 0, img.width, img.height))

        # 6. 创建交互热区
        self._create_hitboxes(nodes, repo_path)

        # 清理临时文件
        svg_path.unlink()
        png_path.unlink()

    def _create_hitboxes(self, nodes: List[Dict], repo_path: Path):
        """创建点击热区

        Args:
            nodes: 节点坐标信息
            repo_path: 仓库路径
        """
        # 获取提交信息
        commits = self._get_commit_info(repo_path, len(nodes))

        # 创建映射
        self.commit_mapping = {}
        for i, node in enumerate(nodes):
            if i < len(commits):
                x, y = node["x"], node["y"]
                r = node["radius"] + 4  # 扩大点击区域

                # 存储热区信息
                self.commit_mapping[(x-r, y-r, x+r, y+r)] = {
                    "index": i,
                    "commit": commits[i],
                    "x": x,
                    "y": y
                }

    def _get_commit_info(self, repo_path: Path, limit: int) -> List[Dict]:
        """获取提交信息

        Args:
            repo_path: 仓库路径
            limit: 限制数量

        Returns:
            提交信息列表
        """
        result = subprocess.run(
            ["git", "log", "--format=%H|%s|%an|%at", f"-n{limit}"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True
        )

        commits = []
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split("|")
                commits.append({
                    "hash": parts[0],
                    "subject": parts[1],
                    "author": parts[2],
                    "timestamp": parts[3]
                })
        return commits

    def on_click(self, event):
        """处理点击事件"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        # 查找点击的提交
        for (x1, y1, x2, y2), info in self.commit_mapping.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                self.show_commit_info(info)
                break

    def on_motion(self, event):
        """处理鼠标移动事件"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        # 更新悬停效果
        for (x1, y1, x2, y2), info in self.commit_mapping.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                # 显示提示信息
                self.canvas.configure(cursor="hand2")
                return

        self.canvas.configure(cursor="")

    def show_commit_info(self, info: Dict):
        """显示提交信息

        Args:
            info: 提交信息
        """
        commit = info["commit"]
        print(f"Commit: {commit['hash'][:7]}")
        print(f"Subject: {commit['subject']}")
        print(f"Author: {commit['author']}")
        print("-" * 40)


# 使用示例
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Git Graph Integration Demo")
    root.geometry("1200x800")

    # 创建交互式图形组件
    graph = InteractiveGraphCanvas(root)
    graph.pack(fill=tk.BOTH, expand=True)

    # 渲染图形
    repo_path = Path.cwd()  # 使用当前目录
    if (repo_path / ".git").exists():
        graph.render_graph(repo_path, num_commits=50)

    root.mainloop()