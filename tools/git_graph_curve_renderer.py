#!/usr/bin/env python3
"""
Git Graph Enhanced Renderer - 精确复现 git-graph 的线条效果
支持贝塞尔曲线、分支/合并的平滑过渡
"""

import tkinter as tk
import subprocess
import math
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import re
import xml.etree.ElementTree as ET


class GitGraphCurveRenderer:
    """Git Graph 曲线渲染器 - 精确复现 SVG 效果"""

    def __init__(self, canvas: tk.Canvas):
        self.canvas = canvas
        self.git_graph_bin = self._find_git_graph()

        # 布局参数（与 git-graph 保持一致）
        self.LANE_WIDTH = 15  # 列宽（SVG 中 x 坐标差）
        self.ROW_HEIGHT = 15  # 行高（SVG 中 y 坐标差）
        self.NODE_RADIUS = 4   # 节点半径
        self.X_OFFSET = 15     # 左边距
        self.Y_OFFSET = 15     # 上边距

        # 颜色方案
        self.COLORS = {
            "blue": "#1E88E5",    # 主分支
            "red": "#E53935",     # 特性分支1
            "green": "#43A047",   # 特性分支2
            "orange": "#FB8C00",  # 特性分支3
            "purple": "#8E24AA",  # 特性分支4
            "brown": "#6D4C41",   # 特性分支5
            "pink": "#D81B60",    # 特性分支6
            "gray": "#757575",    # 特性分支7
        }

        self.nodes_data = []
        self.edges_data = []
        self.hitboxes = []

    def _find_git_graph(self) -> str:
        """查找 git-graph 二进制文件"""
        import shutil

        # 检查项目路径
        project_path = Path(__file__).parent.parent / "src/git-graph/target/release/git-graph"
        if project_path.exists():
            return str(project_path)

        # 检查系统 PATH
        sys_path = shutil.which("git-graph")
        if sys_path:
            return sys_path

        raise FileNotFoundError("git-graph not found")

    def parse_svg_to_canvas(self, repo_path: Path, limit: int = 50):
        """解析 git-graph SVG 并转换为 Canvas 绘图指令"""

        # 生成 SVG
        svg_content = self._generate_svg(repo_path, limit)

        # 解析 SVG
        root = ET.fromstring(svg_content)

        # 清空画布
        self.canvas.delete("all")
        self.nodes_data.clear()
        self.edges_data.clear()
        self.hitboxes.clear()

        # 解析并绘制
        self._parse_and_draw_svg(root)

        # 获取提交信息并关联
        self._associate_commit_data(repo_path, limit)

        # 设置滚动区域
        self._setup_scroll_region()

    def _generate_svg(self, repo_path: Path, limit: int) -> str:
        """使用 git-graph 生成 SVG"""
        result = subprocess.run(
            [self.git_graph_bin, "--svg", "-n", str(limit)],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout

    def _parse_and_draw_svg(self, root: ET.Element):
        """解析 SVG 元素并绘制到 Canvas"""

        # 获取 SVG 命名空间
        ns = {'svg': 'http://www.w3.org/2000/svg'}

        # 1. 先绘制所有线条和路径（边）
        for element in root:
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag

            if tag == "line":
                self._draw_line(element)
            elif tag == "path":
                self._draw_path(element)

        # 2. 再绘制所有圆圈（节点）
        for element in root:
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag

            if tag == "circle":
                self._draw_circle(element)

    def _draw_line(self, element: ET.Element):
        """绘制直线"""
        x1 = float(element.get("x1", 0))
        y1 = float(element.get("y1", 0))
        x2 = float(element.get("x2", 0))
        y2 = float(element.get("y2", 0))
        stroke = element.get("stroke", "black")
        width = float(element.get("stroke-width", 1))

        # 转换颜色
        color = self._convert_color(stroke)

        # 绘制到 Canvas
        self.canvas.create_line(
            x1, y1, x2, y2,
            fill=color,
            width=width * 1.5,  # 稍微加粗以提高可见度
            capstyle=tk.ROUND,
            tags="edge"
        )

        # 存储边数据
        self.edges_data.append({
            "type": "line",
            "x1": x1, "y1": y1,
            "x2": x2, "y2": y2,
            "color": color
        })

    def _draw_path(self, element: ET.Element):
        """绘制路径（贝塞尔曲线）"""
        d = element.get("d", "")
        stroke = element.get("stroke", "black")
        fill = element.get("fill", "none")
        width = float(element.get("stroke-width", 1))

        # 转换颜色
        color = self._convert_color(stroke)

        # 解析路径数据
        points = self._parse_path_data(d)

        if points:
            # 绘制贝塞尔曲线
            self._draw_bezier_curve(points, color, width)

            # 存储边数据
            self.edges_data.append({
                "type": "path",
                "points": points,
                "color": color
            })

    def _parse_path_data(self, d: str) -> List[Tuple[float, float]]:
        """解析 SVG 路径数据

        支持的格式：
        - M x,y - 移动到
        - L x,y - 直线到
        - Q cx,cy,x,y - 二次贝塞尔曲线
        """
        points = []
        commands = re.findall(r'[MLQ][^MLQ]*', d)

        current_x, current_y = 0, 0

        for cmd in commands:
            parts = cmd.strip().split()
            cmd_type = parts[0]

            if cmd_type == 'M':
                # 移动命令
                coords = parts[1].split(',')
                current_x = float(coords[0])
                current_y = float(coords[1])
                points.append(("M", current_x, current_y))

            elif cmd_type == 'L':
                # 直线命令
                coords = parts[1].split(',')
                x = float(coords[0])
                y = float(coords[1])
                points.append(("L", x, y))
                current_x, current_y = x, y

            elif cmd_type == 'Q':
                # 二次贝塞尔曲线
                # 格式：Q cx,cy,ex,ey
                coords_str = ' '.join(parts[1:])
                # 处理可能的格式：Q15,277.5,22.5,277.5 Q30,277.5,30,285
                coords_parts = re.findall(r'Q?(\d+(?:\.\d+)?),(\d+(?:\.\d+)?),(\d+(?:\.\d+)?),(\d+(?:\.\d+)?)', coords_str)

                for coord_set in coords_parts:
                    cx = float(coord_set[0])
                    cy = float(coord_set[1])
                    ex = float(coord_set[2])
                    ey = float(coord_set[3])
                    points.append(("Q", cx, cy, ex, ey))
                    current_x, current_y = ex, ey

        return points

    def _draw_bezier_curve(self, points: List[Tuple], color: str, width: float):
        """绘制贝塞尔曲线"""

        # 将路径点转换为坐标列表
        coords = []

        i = 0
        while i < len(points):
            cmd = points[i]

            if cmd[0] == "M":
                coords.append(cmd[1])
                coords.append(cmd[2])

            elif cmd[0] == "L":
                if not coords:
                    coords.append(cmd[1])
                    coords.append(cmd[2])
                else:
                    # 从上一个点画直线
                    coords.append(cmd[1])
                    coords.append(cmd[2])

            elif cmd[0] == "Q":
                # 二次贝塞尔曲线
                if len(coords) >= 2:
                    start_x = coords[-2]
                    start_y = coords[-1]
                else:
                    start_x, start_y = 0, 0

                cx, cy = cmd[1], cmd[2]
                ex, ey = cmd[3], cmd[4]

                # 生成贝塞尔曲线点
                bezier_points = self._compute_bezier_points(
                    start_x, start_y, cx, cy, ex, ey
                )

                # 添加贝塞尔曲线点
                for bx, by in bezier_points[1:]:  # 跳过起点
                    coords.append(bx)
                    coords.append(by)

            i += 1

        # 绘制平滑曲线
        if len(coords) >= 4:
            self.canvas.create_line(
                coords,
                fill=color,
                width=width * 1.5,
                smooth=True,
                splinesteps=20,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
                tags="edge"
            )

    def _compute_bezier_points(self, x0, y0, cx, cy, x1, y1, steps=10):
        """计算二次贝塞尔曲线上的点"""
        points = []

        for i in range(steps + 1):
            t = i / steps

            # 二次贝塞尔曲线公式
            # B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2
            x = (1-t)**2 * x0 + 2*(1-t)*t * cx + t**2 * x1
            y = (1-t)**2 * y0 + 2*(1-t)*t * cy + t**2 * y1

            points.append((x, y))

        return points

    def _draw_circle(self, element: ET.Element):
        """绘制圆圈（节点）"""
        cx = float(element.get("cx", 0))
        cy = float(element.get("cy", 0))
        r = float(element.get("r", 4))
        fill = element.get("fill", "blue")
        stroke = element.get("stroke", "blue")
        width = float(element.get("stroke-width", 1))

        # 转换颜色
        fill_color = self._convert_color(fill)
        stroke_color = self._convert_color(stroke)

        # 判断是否是合并节点（白色填充）
        is_merge = fill == "white"

        # 绘制到 Canvas
        if is_merge:
            # 合并节点 - 空心圆
            node = self.canvas.create_oval(
                cx - r - 1, cy - r - 1,
                cx + r + 1, cy + r + 1,
                fill="#1E1E1E",  # 深色背景
                outline=stroke_color,
                width=width * 2,
                tags=("node", f"node_{len(self.nodes_data)}")
            )
        else:
            # 普通节点 - 实心圆
            node = self.canvas.create_oval(
                cx - r, cy - r,
                cx + r, cy + r,
                fill=fill_color,
                outline=stroke_color,
                width=width,
                tags=("node", f"node_{len(self.nodes_data)}")
            )

        # 存储节点数据
        node_data = {
            "id": len(self.nodes_data),
            "x": cx,
            "y": cy,
            "radius": r,
            "color": stroke_color,
            "is_merge": is_merge,
            "canvas_id": node
        }
        self.nodes_data.append(node_data)

        # 创建点击热区
        self.hitboxes.append({
            "bbox": (cx - r - 5, cy - r - 5, cx + r + 5, cy + r + 5),
            "node": node_data
        })

        # 绑定事件
        self.canvas.tag_bind(node, "<Enter>", lambda e: self._on_node_hover(node_data))
        self.canvas.tag_bind(node, "<Leave>", lambda e: self._on_node_leave())
        self.canvas.tag_bind(node, "<Button-1>", lambda e: self._on_node_click(node_data))

    def _convert_color(self, svg_color: str) -> str:
        """转换 SVG 颜色到 Tkinter 颜色"""
        color_map = {
            "blue": "#1E88E5",
            "red": "#E53935",
            "green": "#43A047",
            "orange": "#FB8C00",
            "purple": "#8E24AA",
            "brown": "#6D4C41",
            "pink": "#D81B60",
            "gray": "#757575",
            "white": "#FFFFFF",
            "black": "#000000"
        }
        return color_map.get(svg_color, svg_color)

    def _associate_commit_data(self, repo_path: Path, limit: int):
        """关联提交数据到节点"""

        # 获取提交信息
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

        # 关联到节点
        for i, node in enumerate(self.nodes_data):
            if i < len(commits):
                node["commit"] = commits[i]

    def _setup_scroll_region(self):
        """设置滚动区域"""
        if self.nodes_data:
            max_x = max(n["x"] for n in self.nodes_data) + 100
            max_y = max(n["y"] for n in self.nodes_data) + 50
            self.canvas.configure(scrollregion=(0, 0, max_x, max_y))

    def _on_node_hover(self, node: Dict):
        """节点悬停事件"""
        # 高亮节点
        self.canvas.itemconfig(
            node["canvas_id"],
            width=3
        )

        # 显示提示
        if "commit" in node:
            commit = node["commit"]
            text = f"{commit['hash'][:7]} - {commit['subject'][:50]}"

            self.tooltip = self.canvas.create_text(
                node["x"] + 15, node["y"],
                text=text,
                anchor=tk.W,
                fill="#FFFFFF",
                font=("Monaco", 9),
                tags="tooltip"
            )

            # 添加背景
            bbox = self.canvas.bbox(self.tooltip)
            if bbox:
                self.tooltip_bg = self.canvas.create_rectangle(
                    bbox[0] - 2, bbox[1] - 2,
                    bbox[2] + 2, bbox[3] + 2,
                    fill="#333333",
                    outline="#555555",
                    tags="tooltip"
                )
                self.canvas.tag_raise(self.tooltip)

    def _on_node_leave(self):
        """节点离开事件"""
        # 删除提示
        self.canvas.delete("tooltip")

        # 恢复节点宽度
        for node in self.nodes_data:
            self.canvas.itemconfig(node["canvas_id"], width=1)

    def _on_node_click(self, node: Dict):
        """节点点击事件"""
        if "commit" in node:
            commit = node["commit"]
            print(f"=" * 60)
            print(f"Commit: {commit['hash'][:7]}")
            print(f"Subject: {commit['subject']}")
            print(f"Author: {commit['author']}")
            print(f"Position: ({node['x']}, {node['y']})")
            print(f"Is Merge: {node['is_merge']}")
            print(f"=" * 60)


class EnhancedGitGraphGUI(tk.Frame):
    """增强的 Git Graph GUI 组件"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.setup_ui()
        self.renderer = GitGraphCurveRenderer(self.canvas)

    def setup_ui(self):
        """设置 UI"""
        # 工具栏
        toolbar = tk.Frame(self, bg="#2B2B2B")
        toolbar.pack(fill=tk.X, padx=5, pady=5)

        tk.Button(
            toolbar,
            text="刷新",
            command=self.refresh_graph,
            bg="#3C3C3C",
            fg="#CCCCCC"
        ).pack(side=tk.LEFT, padx=2)

        tk.Label(
            toolbar,
            text="提交数:",
            bg="#2B2B2B",
            fg="#CCCCCC"
        ).pack(side=tk.LEFT, padx=(10, 2))

        self.limit_var = tk.StringVar(value="50")
        tk.Spinbox(
            toolbar,
            from_=10, to=200,
            textvariable=self.limit_var,
            width=5,
            bg="#3C3C3C",
            fg="#CCCCCC"
        ).pack(side=tk.LEFT, padx=2)

        # 画布容器
        canvas_frame = tk.Frame(self, bg="#1E1E1E")
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        # 画布
        self.canvas = tk.Canvas(
            canvas_frame,
            bg="#1E1E1E",
            highlightthickness=0
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 滚动条
        v_scrollbar = tk.Scrollbar(
            canvas_frame,
            orient=tk.VERTICAL,
            command=self.canvas.yview
        )
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        h_scrollbar = tk.Scrollbar(
            self,
            orient=tk.HORIZONTAL,
            command=self.canvas.xview
        )
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.configure(
            yscrollcommand=v_scrollbar.set,
            xscrollcommand=h_scrollbar.set
        )

    def refresh_graph(self):
        """刷新图形"""
        repo_path = Path.cwd()

        if not (repo_path / ".git").exists():
            print("当前目录不是 Git 仓库")
            return

        try:
            limit = int(self.limit_var.get())
        except ValueError:
            limit = 50

        # 渲染图形
        self.renderer.parse_svg_to_canvas(repo_path, limit)

    def load_repository(self, repo_path: Path, limit: int = 50):
        """加载指定仓库"""
        if (repo_path / ".git").exists():
            self.renderer.parse_svg_to_canvas(repo_path, limit)
        else:
            print(f"错误：{repo_path} 不是 Git 仓库")


# 测试程序
if __name__ == "__main__":
    # 创建主窗口
    root = tk.Tk()
    root.title("Git Graph Enhanced - 精确线条渲染")
    root.geometry("1200x800")

    # 设置深色主题
    root.configure(bg="#1E1E1E")

    # 创建增强的 Git Graph 组件
    graph_gui = EnhancedGitGraphGUI(root, bg="#1E1E1E")
    graph_gui.pack(fill=tk.BOTH, expand=True)

    # 自动加载当前仓库
    current_repo = Path.cwd()
    if (current_repo / ".git").exists():
        root.after(100, lambda: graph_gui.load_repository(current_repo, 50))

    # 运行
    root.mainloop()