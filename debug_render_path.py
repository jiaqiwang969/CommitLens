#!/usr/bin/env python3
"""Find out which render path is actually being used"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "tools"))

# Monkey-patch ALL render methods to log
from sboxgen_gui import SboxgenGUI

# Store original methods
orig_perfect = SboxgenGUI._draw_interactive_graph_perfect
orig_enhanced = SboxgenGUI._draw_interactive_graph_safe_enhanced
orig_fallback = SboxgenGUI._draw_interactive_graph_fallback

def patched_perfect(self, canvas, data):
    print("\n!!!! USING PERFECT RENDER !!!!")
    return orig_perfect(self, canvas, data)

def patched_enhanced(self, canvas, data):
    print("\n!!!! USING ENHANCED RENDER !!!!")
    print(f"Data has {len(data.get('nodes', []))} nodes, {len(data.get('edges', []))} edges")
    return orig_enhanced(self, canvas, data)

def patched_fallback(self, canvas, data):
    print("\n!!!! USING FALLBACK RENDER !!!!")
    print(f"Data has {len(data.get('nodes', []))} nodes, {len(data.get('edges', []))} edges")

    # Check edges
    edges = data.get('edges', [])
    nodes = data.get('nodes', [])

    for e in edges[:5]:
        from_idx = e.get('from', -1)
        to_idx = e.get('to', -1)
        if 0 <= from_idx < len(nodes) and 0 <= to_idx < len(nodes):
            from_node = nodes[from_idx]
            to_node = nodes[to_idx]
            from_col = from_node.get('column', 0)
            to_col = to_node.get('column', 0)

            if from_col != to_col:
                print(f"  SHOULD DRAW CURVE: node {from_idx} (col {from_col}) -> node {to_idx} (col {to_col})")
            else:
                print(f"  straight line: node {from_idx} (col {from_col}) -> node {to_idx} (col {to_col})")

    return orig_fallback(self, canvas, data)

# Apply patches
SboxgenGUI._draw_interactive_graph_perfect = patched_perfect
SboxgenGUI._draw_interactive_graph_safe_enhanced = patched_enhanced
SboxgenGUI._draw_interactive_graph_fallback = patched_fallback

# Now run the GUI
import tkinter as tk

root = tk.Tk()
root.title("DEBUG - Which render path?")
root.geometry("1000x600")

gui = SboxgenGUI(root)
gui.repo_path = Path.cwd() / ".workspace/rust-project"
gui.repo_var.set(str(gui.repo_path))

def trigger():
    print("\n" + "="*60)
    print("TRIGGERING RENDER")
    print("="*60)
    gui._interactive_graph_render(limit_snap=10)

root.after(1000, trigger)
root.mainloop()