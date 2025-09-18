#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 Codex Output 查看器功能"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.sboxgen_gui import SboxgenGUI
import tkinter as tk
from pathlib import Path

def test_codex_viewer():
    """测试 Codex Output 查看器"""
    print("启动 GUI 测试...")

    # 创建主窗口
    root = tk.Tk()
    root.title("Codex Output 查看器测试")
    root.geometry("1200x800")

    # 创建 GUI 实例
    print("创建 GUI 实例...")
    gui = SboxgenGUI(root)

    # 检查方法
    print("\n方法检查:")
    print(f"  _append_log 方法存在: {hasattr(gui, '_append_log')}")
    print(f"  log 方法存在: {hasattr(gui, 'log')}")
    print(f"  _load_codex_file 方法存在: {hasattr(gui, '_load_codex_file')}")

    # 设置测试文件路径
    test_file = "/Users/jqwang/104-CommitLens-codex/.sboxes/001-84a2fb2/codex_output.txt"
    if Path(test_file).exists():
        print(f"\n测试文件存在: {test_file}")
        # 设置文件路径
        gui.codex_file_var.set(test_file)
        print("已设置文件路径到 codex_file_var")

        # 切换到 Codex Output 标签页
        # 找到 notebook 并切换
        for widget in root.winfo_children():
            if isinstance(widget, tk.Widget):
                # 递归查找 notebook
                def find_notebook(parent):
                    for child in parent.winfo_children():
                        if 'notebook' in str(type(child)).lower():
                            return child
                        result = find_notebook(child)
                        if result:
                            return result
                    return None

                notebook = find_notebook(root)
                if notebook:
                    # 切换到最后一个标签页 (Codex Output)
                    try:
                        notebook.select(4)  # 第5个标签页 (索引从0开始)
                        print("已切换到 Codex Output 标签页")
                    except:
                        print("无法切换标签页")
                    break

        # 尝试直接调用加载方法
        print("\n尝试加载文件...")
        try:
            gui._load_codex_file()
            print("文件加载成功!")
            print(f"解析到 {len(gui.codex_messages)} 条消息")
        except AttributeError as e:
            print(f"AttributeError: {e}")
            import traceback
            traceback.print_exc()
        except Exception as e:
            print(f"其他错误: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"\n测试文件不存在: {test_file}")

    print("\n启动 GUI 主循环...")
    print("请手动测试 Codex Output 标签页的功能")
    print("提示: 切换到 'Codex Output' 标签页，点击 '加载' 按钮")

    # 启动主循环
    root.mainloop()

if __name__ == "__main__":
    test_codex_viewer()