#!/usr/bin/env python3
"""
Git Graph FFI Integration - 通过 Rust FFI 获取图形数据
这是最高效的集成方案
"""

import ctypes
import json
import sys
from pathlib import Path
from typing import Dict, Optional
import tkinter as tk


class GitGraphFFI:
    """Git Graph Rust FFI 绑定"""

    def __init__(self, lib_path: str = None):
        """初始化 FFI 绑定

        Args:
            lib_path: 动态库路径
        """
        self.lib = self._load_library(lib_path)
        self._setup_functions()

    def _load_library(self, lib_path: str = None) -> ctypes.CDLL:
        """加载动态库"""
        if lib_path:
            return ctypes.CDLL(lib_path)

        # 自动检测库文件
        if sys.platform == "darwin":
            lib_name = "libgit_graph.dylib"
        elif sys.platform.startswith("win"):
            lib_name = "git_graph.dll"
        else:
            lib_name = "libgit_graph.so"

        # 查找库文件
        search_paths = [
            Path(__file__).parent.parent / "src/git-graph/target/release" / lib_name,
            Path(__file__).parent.parent / "target/release" / lib_name,
            Path.cwd() / lib_name,
        ]

        for path in search_paths:
            if path.exists():
                return ctypes.CDLL(str(path))

        raise FileNotFoundError(f"Cannot find {lib_name}")

    def _setup_functions(self):
        """设置函数签名"""
        # git_graph_layout_json
        self.lib.git_graph_layout_json.argtypes = [
            ctypes.c_char_p,  # repo_path
            ctypes.c_size_t,  # limit
        ]
        self.lib.git_graph_layout_json.restype = ctypes.c_void_p

        # git_graph_free_string
        self.lib.git_graph_free_string.argtypes = [ctypes.c_void_p]
        self.lib.git_graph_free_string.restype = None

    def get_layout(self, repo_path: Path, limit: int = 50) -> Dict:
        """获取图形布局数据

        Args:
            repo_path: 仓库路径
            limit: 提交数量限制

        Returns:
            布局数据字典
        """
        # 调用 FFI
        path_bytes = str(repo_path).encode('utf-8')
        ptr = self.lib.git_graph_layout_json(path_bytes, limit)

        if not ptr:
            raise RuntimeError("Failed to generate layout")

        try:
            # 获取 JSON 字符串
            json_str = ctypes.string_at(ptr).decode('utf-8')
            return json.loads(json_str)
        finally:
            # 释放内存
            self.lib.git_graph_free_string(ptr)


class OptimizedGraphRenderer:
    """优化的图形渲染器 - 使用 FFI 数据"""

    def __init__(self, canvas: tk.Canvas):
        self.canvas = canvas
        self.ffi = None
        self.current_data = None
        self.hover_item = None
        self.selected_node = None

    def initialize_ffi(self, lib_path: str = None):
        """初始化 FFI"""
        try:
            self.ffi = GitGraphFFI(lib_path)
            return True
        except Exception as e:
            print(f"FFI initialization failed: {e}")
            return False

    def render_repository(self, repo_path: Path, limit: int = 50):
        """渲染仓库图形

        Args:
            repo_path: 仓库路径
            limit: 显示的提交数
        """
        if not self.ffi:
            print("FFI not initialized, falling back to command line")
            self._render_fallback(repo_path, limit)
            return

        # 获取布局数据
        try:
            data = self.ffi.get_layout(repo_path, limit)
            self.current_data = data
            self._render_graph(data)
        except Exception as e:
            print(f"FFI render failed: {e}, using fallback")
            self._render_fallback(repo_path, limit)

    def _render_graph(self, data: Dict):
        """渲染图形数据"""
        self.canvas.delete("all")

        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        # 布局参数
        settings = {
            "x_offset": 60,
            "y_offset": 30,
            "lane_spacing": 40,
            "row_spacing": 28,
            "node_radius": 6,
            "colors": [
                "#2196F3",  # 蓝色
                "#FF9800",  # 橙色
                "#4CAF50",  # 绿色
                "#F44336",  # 红色
                "#9C27B0",  # 紫色
                "#795548",  # 棕色
            ]
        }

        # 计算位置
        positions = {}
        for node in nodes:
            idx = node["index"]
            col = node["column"]
            x = settings["x_offset"] + col * settings["lane_spacing"]
            y = settings["y_offset"] + idx * settings["row_spacing"]
            positions[idx] = (x, y)
            node["_x"] = x
            node["_y"] = y

        # 绘制网格线（可选）
        if len(nodes) > 0:
            for i in range(len(nodes)):
                y = settings["y_offset"] + i * settings["row_spacing"]
                self.canvas.create_line(
                    0, y,
                    settings["x_offset"] + 5 * settings["lane_spacing"], y,
                    fill="#333333",
                    dash=(2, 4)
                )

        # 绘制边
        for edge in edges:
            from_idx = edge["from"]
            to_idx = edge.get("to")

            if to_idx is None:
                continue

            if from_idx in positions and to_idx in positions:
                x1, y1 = positions[from_idx]
                x2, y2 = positions[to_idx]

                # 获取颜色
                from_node = nodes[from_idx]
                color = settings["colors"][from_node["column"] % len(settings["colors"])]

                # 绘制连线
                if abs(x1 - x2) > settings["lane_spacing"] / 2:
                    # 曲线连接
                    self._draw_curved_edge(x1, y1, x2, y2, color)
                else:
                    # 直线连接
                    self.canvas.create_line(
                        x1, y1, x2, y2,
                        fill=color,
                        width=2,
                        capstyle=tk.ROUND
                    )

        # 绘制节点
        for node in nodes:
            self._draw_node(node, settings)

        # 设置滚动区域
        max_x = max((n.get("_x", 0) for n in nodes), default=200) + 200
        max_y = max((n.get("_y", 0) for n in nodes), default=200) + 100
        self.canvas.configure(scrollregion=(0, 0, max_x, max_y))

    def _draw_node(self, node: Dict, settings: Dict):
        """绘制单个节点"""
        x = node.get("_x", 0)
        y = node.get("_y", 0)
        r = settings["node_radius"]

        # 选择颜色
        color = settings["colors"][node["column"] % len(settings["colors"])]

        # 绘制节点
        if node.get("is_merge"):
            # 合并提交 - 空心圆
            item = self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill="#1e1e1e",
                outline=color,
                width=2,
                tags=("node", f"node_{node['index']}")
            )
        else:
            # 普通提交 - 实心圆
            item = self.canvas.create_oval(
                x - r, y - r, x + r, y + r,
                fill=color,
                outline=color,
                tags=("node", f"node_{node['index']}")
            )

        # 绑定事件
        self.canvas.tag_bind(item, "<Enter>", lambda e: self._on_node_hover(node))
        self.canvas.tag_bind(item, "<Leave>", lambda e: self._on_node_leave(node))
        self.canvas.tag_bind(item, "<Button-1>", lambda e: self._on_node_click(node))

    def _draw_curved_edge(self, x1: float, y1: float, x2: float, y2: float, color: str):
        """绘制曲线边"""
        # 计算控制点
        mid_y = (y1 + y2) / 2

        # 创建平滑曲线
        points = [x1, y1, x1, mid_y, x2, mid_y, x2, y2]
        self.canvas.create_line(
            points,
            fill=color,
            width=2,
            smooth=True,
            splinesteps=20,
            capstyle=tk.ROUND
        )

    def _on_node_hover(self, node: Dict):
        """节点悬停事件"""
        x = node.get("_x", 0)
        y = node.get("_y", 0)

        # 显示提示
        if self.hover_item:
            self.canvas.delete(self.hover_item)

        text = f"{node['short']} - {node['subject'][:50]}"
        self.hover_item = self.canvas.create_text(
            x + 15, y,
            text=text,
            anchor=tk.W,
            fill="#FFFFFF",
            font=("Consolas", 10),
            tags="tooltip"
        )

        # 改变光标
        self.canvas.configure(cursor="hand2")

    def _on_node_leave(self, node: Dict):
        """节点离开事件"""
        if self.hover_item:
            self.canvas.delete(self.hover_item)
            self.hover_item = None

        self.canvas.configure(cursor="")

    def _on_node_click(self, node: Dict):
        """节点点击事件"""
        print(f"Commit: {node['id'][:7]}")
        print(f"Subject: {node['subject']}")
        print(f"Author: {node['author']}")
        print(f"Column: {node['column']}")
        print("-" * 60)

        # 高亮选中的节点
        if self.selected_node:
            self.canvas.delete("selection")

        x = node.get("_x", 0)
        y = node.get("_y", 0)
        r = 10

        self.canvas.create_oval(
            x - r, y - r, x + r, y + r,
            outline="#FFD700",
            width=3,
            tags="selection"
        )
        self.selected_node = node

    def _render_fallback(self, repo_path: Path, limit: int):
        """降级渲染方案"""
        # 使用命令行工具作为后备方案
        import subprocess

        try:
            result = subprocess.run(
                ["git", "log", "--graph", "--oneline", f"-n{limit}"],
                cwd=str(repo_path),
                capture_output=True,
                text=True
            )

            # 在画布上显示文本
            self.canvas.delete("all")
            self.canvas.create_text(
                10, 10,
                text=result.stdout,
                anchor=tk.NW,
                fill="#CCCCCC",
                font=("Courier", 10)
            )
        except Exception as e:
            print(f"Fallback render failed: {e}")


# 使用示例
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Git Graph FFI Integration")
    root.geometry("1000x700")

    # 创建画布
    canvas = tk.Canvas(root, bg="#1e1e1e")
    canvas.pack(fill=tk.BOTH, expand=True)

    # 添加滚动条
    v_scroll = tk.Scrollbar(canvas, orient=tk.VERTICAL)
    v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    h_scroll = tk.Scrollbar(canvas, orient=tk.HORIZONTAL)
    h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

    canvas.configure(
        yscrollcommand=v_scroll.set,
        xscrollcommand=h_scroll.set
    )
    v_scroll.configure(command=canvas.yview)
    h_scroll.configure(command=canvas.xview)

    # 创建渲染器
    renderer = OptimizedGraphRenderer(canvas)

    # 尝试初始化 FFI
    if renderer.initialize_ffi():
        print("FFI initialized successfully")
    else:
        print("Using fallback rendering")

    # 渲染当前仓库
    repo = Path.cwd()
    if (repo / ".git").exists():
        renderer.render_repository(repo, limit=50)

    root.mainloop()