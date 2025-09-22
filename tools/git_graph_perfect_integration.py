#!/usr/bin/env python3
"""
Git Graph 完美集成方案 - 直接替换到 sboxgen_gui.py
这个模块可以无缝集成到现有的 GUI 中
"""

import tkinter as tk
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re


class GitGraphPerfectIntegration:
    """完美集成的 Git Graph 渲染器

    特点：
    1. 精确复现 git-graph 的贝塞尔曲线
    2. 支持所有分支/合并的视觉效果
    3. 可直接替换到 sboxgen_gui.py 的 _draw_interactive_graph 方法
    """

    def __init__(self):
        self.git_graph_bin = None
        self.current_canvas = None
        self.hover_item = None
        self.label_items = []

    def _ensure_git_graph_bin(self) -> str:
        """确保 git-graph 二进制可用（兼容原有代码）"""
        if self.git_graph_bin:
            return self.git_graph_bin

        import shutil
        import os

        # 1) 环境变量
        p = os.environ.get("SBOXGEN_GIT_GRAPH")
        if p and Path(p).exists():
            self.git_graph_bin = p
            return p

        # 2) 系统 PATH
        p = shutil.which("git-graph")
        if p:
            self.git_graph_bin = p
            return p

        # 3) 项目内路径
        search_paths = [
            Path(__file__).parent.parent / "src/git-graph/target/release/git-graph",
            Path(__file__).parent.parent / "vendor/git-graph/bin/git-graph",
        ]
        for path in search_paths:
            if path.exists():
                self.git_graph_bin = str(path)
                return str(path)

        raise FileNotFoundError("git-graph binary not found")

    def render_interactive_graph(self, canvas: tk.Canvas, repo_path: Path,
                                limit: Optional[int] = None) -> Dict:
        """渲染交互式图形（主入口）

        Args:
            canvas: Tkinter Canvas 对象
            repo_path: 仓库路径
            limit: 提交数限制

        Returns:
            渲染数据字典
        """
        self.current_canvas = canvas

        # 获取 git-graph 二进制
        bin_path = self._ensure_git_graph_bin()

        # 生成 SVG
        svg_data = self._generate_svg(bin_path, repo_path, limit or 50)

        # 解析并渲染
        graph_data = self._parse_and_render_svg(svg_data, canvas)

        # 关联提交信息
        self._enrich_with_commit_info(graph_data, repo_path, limit or 50)

        # 设置滚动区域
        self._configure_scroll_region(canvas, graph_data)

        return graph_data

    def _generate_svg(self, bin_path: str, repo_path: Path, limit: int) -> str:
        """生成 SVG 数据"""
        result = subprocess.run(
            [bin_path, "--svg", "-n", str(limit)],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            env=self._spawn_env()
        )
        if result.returncode != 0:
            raise RuntimeError(f"git-graph failed: {result.stderr}")
        return result.stdout

    def _spawn_env(self) -> dict:
        """生成子进程环境（兼容原代码）"""
        import os
        env = os.environ.copy()
        return env

    def _parse_and_render_svg(self, svg_content: str, canvas: tk.Canvas) -> Dict:
        """解析 SVG 并渲染到 Canvas"""

        # 清空画布
        canvas.delete("all")

        # 解析 SVG
        root = ET.fromstring(svg_content)

        # 数据结构
        graph_data = {
            "nodes": [],
            "edges": [],
            "hitboxes": [],
            "meta": {}
        }

        # 深色主题颜色映射
        color_map = {
            "blue": "#2196F3",
            "red": "#F44336",
            "green": "#4CAF50",
            "orange": "#FF9800",
            "purple": "#9C27B0",
            "brown": "#795548",
            "pink": "#E91E63",
            "gray": "#9E9E9E",
            "white": "#FFFFFF",
            "black": "#000000"
        }

        # 渲染参数
        line_width_multiplier = 1.5  # 线条加粗系数
        node_hover_radius = 8         # 悬停时的节点半径

        # 1. 绘制边（线条和路径）
        for element in root:
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag

            if tag == "line":
                # 直线边
                x1 = float(element.get("x1", 0))
                y1 = float(element.get("y1", 0))
                x2 = float(element.get("x2", 0))
                y2 = float(element.get("y2", 0))
                stroke = element.get("stroke", "black")
                width = float(element.get("stroke-width", 1))

                color = color_map.get(stroke, stroke)

                canvas.create_line(
                    x1, y1, x2, y2,
                    fill=color,
                    width=width * line_width_multiplier,
                    capstyle=tk.ROUND,
                    tags="edge"
                )

                graph_data["edges"].append({
                    "type": "line",
                    "points": [(x1, y1), (x2, y2)],
                    "color": color
                })

            elif tag == "path":
                # 贝塞尔曲线
                d = element.get("d", "")
                stroke = element.get("stroke", "black")
                width = float(element.get("stroke-width", 1))

                color = color_map.get(stroke, stroke)

                # 解析路径并转换为 Canvas 坐标
                coords = self._svg_path_to_canvas_coords(d)

                if len(coords) >= 4:
                    canvas.create_line(
                        coords,
                        fill=color,
                        width=width * line_width_multiplier,
                        smooth=True,
                        splinesteps=20,
                        capstyle=tk.ROUND,
                        joinstyle=tk.ROUND,
                        tags="edge"
                    )

                    graph_data["edges"].append({
                        "type": "path",
                        "path": d,
                        "color": color
                    })

        # 2. 绘制节点（圆圈）
        node_index = 0
        for element in root:
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag

            if tag == "circle":
                cx = float(element.get("cx", 0))
                cy = float(element.get("cy", 0))
                r = float(element.get("r", 4))
                fill = element.get("fill", "blue")
                stroke = element.get("stroke", "blue")
                width = float(element.get("stroke-width", 1))

                fill_color = color_map.get(fill, fill)
                stroke_color = color_map.get(stroke, stroke)

                # 判断是否是合并节点
                is_merge = fill == "white"

                # 绘制节点
                if is_merge:
                    # 合并节点 - 空心圆
                    item = canvas.create_oval(
                        cx - r - 1, cy - r - 1,
                        cx + r + 1, cy + r + 1,
                        fill="#2a2a2a",  # 背景色
                        outline=stroke_color,
                        width=width * 2,
                        tags=("node", f"node_{node_index}")
                    )
                else:
                    # 普通节点 - 实心圆
                    item = canvas.create_oval(
                        cx - r, cy - r,
                        cx + r, cy + r,
                        fill=fill_color,
                        outline=stroke_color,
                        width=width,
                        tags=("node", f"node_{node_index}")
                    )

                # 存储节点数据
                node_data = {
                    "index": node_index,
                    "x": cx,
                    "y": cy,
                    "radius": r,
                    "color": stroke_color,
                    "is_merge": is_merge,
                    "canvas_id": item,
                    "column": int((cx - 15) / 15)  # 根据 x 坐标计算列
                }

                graph_data["nodes"].append(node_data)

                # 创建点击热区
                graph_data["hitboxes"].append({
                    "bbox": (cx - r - 5, cy - r - 5, cx + r + 5, cy + r + 5),
                    "node": node_data
                })

                node_index += 1

        # 3. 绑定事件
        self._bind_canvas_events(canvas, graph_data)

        return graph_data

    def _svg_path_to_canvas_coords(self, path: str) -> List[float]:
        """将 SVG 路径转换为 Canvas 坐标列表"""
        coords = []

        # 解析 SVG 路径命令
        # 示例: "M15,270 L15,270 Q15,277.5,22.5,277.5 Q30,277.5,30,285 L30,300"
        commands = re.findall(r'[MLQ][^MLQ]*', path)

        for cmd in commands:
            parts = cmd.strip()
            cmd_type = parts[0]

            if cmd_type == 'M':
                # 移动到
                match = re.search(r'(\d+(?:\.\d+)?),(\d+(?:\.\d+)?)', parts)
                if match:
                    coords.extend([float(match.group(1)), float(match.group(2))])

            elif cmd_type == 'L':
                # 直线到
                match = re.search(r'(\d+(?:\.\d+)?),(\d+(?:\.\d+)?)', parts)
                if match:
                    coords.extend([float(match.group(1)), float(match.group(2))])

            elif cmd_type == 'Q':
                # 二次贝塞尔曲线 - 生成插值点
                matches = re.findall(r'(\d+(?:\.\d+)?),(\d+(?:\.\d+)?)', parts)
                if len(matches) == 2:
                    # 控制点和终点
                    cx, cy = float(matches[0][0]), float(matches[0][1])
                    ex, ey = float(matches[1][0]), float(matches[1][1])

                    # 获取起点（上一个点）
                    if len(coords) >= 2:
                        sx, sy = coords[-2], coords[-1]
                    else:
                        sx, sy = 0, 0

                    # 生成贝塞尔曲线插值点
                    for t in [0.2, 0.4, 0.6, 0.8, 1.0]:
                        x = (1-t)**2 * sx + 2*(1-t)*t * cx + t**2 * ex
                        y = (1-t)**2 * sy + 2*(1-t)*t * cy + t**2 * ey
                        coords.extend([x, y])

        return coords

    def _enrich_with_commit_info(self, graph_data: Dict, repo_path: Path, limit: int):
        """添加提交信息到节点"""

        # 获取提交信息
        result = subprocess.run(
            ["git", "log", "--format=%H%x01%s%x01%an%x01%at", f"-n{limit}"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            env=self._spawn_env()
        )

        commits = []
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split("\x01")
                if len(parts) >= 4:
                    commits.append({
                        "hash": parts[0],
                        "subject": parts[1],
                        "author": parts[2],
                        "timestamp": parts[3],
                        "short": parts[0][:7]
                    })

        # 关联到节点
        for i, node in enumerate(graph_data["nodes"]):
            if i < len(commits):
                node.update(commits[i])

    def _configure_scroll_region(self, canvas: tk.Canvas, graph_data: Dict):
        """配置滚动区域"""
        if graph_data["nodes"]:
            max_x = max(n["x"] for n in graph_data["nodes"]) + 100
            max_y = max(n["y"] for n in graph_data["nodes"]) + 50
            canvas.configure(scrollregion=(0, 0, max_x, max_y))

    def _bind_canvas_events(self, canvas: tk.Canvas, graph_data: Dict):
        """绑定画布事件"""

        def on_click(event):
            x = canvas.canvasx(event.x)
            y = canvas.canvasy(event.y)

            for hitbox in graph_data["hitboxes"]:
                bbox = hitbox["bbox"]
                if bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]:
                    node = hitbox["node"]
                    self._on_node_click(canvas, node)
                    break
            else:
                # 点击空白处，清除标签
                self._clear_label(canvas)

        def on_motion(event):
            x = canvas.canvasx(event.x)
            y = canvas.canvasy(event.y)

            # 查找悬停的节点
            hover_node = None
            for hitbox in graph_data["hitboxes"]:
                bbox = hitbox["bbox"]
                if bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]:
                    hover_node = hitbox["node"]
                    break

            # 更新悬停效果
            self._update_hover_effect(canvas, hover_node)

        canvas.bind("<Button-1>", on_click)
        canvas.bind("<Motion>", on_motion)

    def _on_node_click(self, canvas: tk.Canvas, node: Dict):
        """处理节点点击"""

        # 显示标签
        self._show_label(canvas, node)

        # 打印信息（可替换为其他操作）
        if "hash" in node:
            print(f"Clicked: {node['short']} - {node.get('subject', '')}")

    def _show_label(self, canvas: tk.Canvas, node: Dict):
        """显示节点标签"""
        self._clear_label(canvas)

        if "subject" not in node:
            return

        # 构建标签文本
        text_parts = [node.get("short", "")]
        if node.get("subject"):
            text_parts.append(node["subject"][:60])
        if node.get("author"):
            text_parts.append(f"by {node['author']}")

        text = " | ".join(text_parts)

        # 创建标签
        x = node["x"] + 15
        y = node["y"]

        # 文本
        text_id = canvas.create_text(
            x, y,
            text=text,
            anchor=tk.W,
            fill="#E0E0E0",
            font=("Monaco", 10),
            tags="label"
        )

        # 背景
        bbox = canvas.bbox(text_id)
        if bbox:
            bg_id = canvas.create_rectangle(
                bbox[0] - 4, bbox[1] - 2,
                bbox[2] + 4, bbox[3] + 2,
                fill="#2a2a2a",
                outline="#555555",
                tags="label"
            )
            canvas.tag_raise(text_id)
            self.label_items = [bg_id, text_id]

    def _clear_label(self, canvas: tk.Canvas):
        """清除标签"""
        canvas.delete("label")
        if self.label_items:
            self.label_items.clear()

    def _update_hover_effect(self, canvas: tk.Canvas, hover_node: Optional[Dict]):
        """更新悬停效果"""

        # 删除旧的悬停效果
        if self.hover_item:
            canvas.delete(self.hover_item)
            self.hover_item = None

        # 创建新的悬停效果
        if hover_node:
            x = hover_node["x"]
            y = hover_node["y"]
            r = hover_node["radius"] + 4

            self.hover_item = canvas.create_oval(
                x - r, y - r, x + r, y + r,
                outline="#2196F3",
                width=2,
                tags="hover"
            )

            # 改变光标
            canvas.configure(cursor="hand2")
        else:
            canvas.configure(cursor="")


# 集成到现有 GUI 的辅助函数
def integrate_perfect_graph(gui_instance, canvas, repo_path, limit=50):
    """将完美渲染集成到现有 GUI

    使用方法：
    在 sboxgen_gui.py 中：

    from git_graph_perfect_integration import GitGraphPerfectIntegration, integrate_perfect_graph

    # 在 _interactive_graph_render 方法中：
    def _interactive_graph_render(self, limit_snap=None):
        integrate_perfect_graph(self, self.exec_graph_canvas, self.repo_path, limit_snap)
    """

    # 创建渲染器
    if not hasattr(gui_instance, '_perfect_graph_renderer'):
        gui_instance._perfect_graph_renderer = GitGraphPerfectIntegration()

    # 渲染
    renderer = gui_instance._perfect_graph_renderer
    graph_data = renderer.render_interactive_graph(canvas, repo_path, limit)

    # 存储数据供其他功能使用
    gui_instance._igraph_hitboxes = graph_data["hitboxes"]
    gui_instance._igraph_nodes_xy = [(n["x"], n["y"], n["radius"], n)
                                     for n in graph_data["nodes"]]

    return graph_data


# 测试代码
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Git Graph Perfect Integration Test")
    root.geometry("1000x700")

    # 创建画布
    canvas = tk.Canvas(root, bg="#2a2a2a")
    canvas.pack(fill=tk.BOTH, expand=True)

    # 创建渲染器
    renderer = GitGraphPerfectIntegration()

    # 渲染当前仓库
    repo = Path.cwd()
    if (repo / ".git").exists():
        graph_data = renderer.render_interactive_graph(canvas, repo, 50)
        print(f"Rendered {len(graph_data['nodes'])} nodes, {len(graph_data['edges'])} edges")

    root.mainloop()