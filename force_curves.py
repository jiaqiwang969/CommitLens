#!/usr/bin/env python3
"""Force curves to appear by patching the GUI directly"""

import tkinter as tk
from pathlib import Path
import sys

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent / "tools"))

from sboxgen_gui import SboxgenGUI

# Monkey-patch the rendering to force curves
original_fallback = SboxgenGUI._draw_interactive_graph_fallback

def patched_fallback(self, canvas: tk.Canvas, data: dict):
    """Patched version that forces curves for testing"""
    canvas.delete('all')
    nodes = data.get('nodes', [])
    edges = data.get('edges', [])
    n = len(nodes)
    if n == 0:
        return

    # Layout params
    y_step = 28
    lane_dx = 90
    x_offset = 80
    y_offset = 24

    # Build dict idx->node
    idx_map = {nd['idx']: nd for nd in nodes}

    # FORCE different columns for testing
    print("\n[PATCH] Forcing columns for curve testing:")
    for i, nd in enumerate(nodes):
        old_col = nd.get('column', 0)
        # Force test-curves branch to column 1
        if 'test-curves' in nd.get('branch', '') or 'test curve' in nd.get('subject', '').lower():
            nd['column'] = 1
            print(f"  Node {i}: '{nd.get('subject', '')[:30]}' -> column 1 (was {old_col})")
        else:
            nd['column'] = 0
            print(f"  Node {i}: '{nd.get('subject', '')[:30]}' -> column 0 (was {old_col})")

    # Now call original with modified data
    original_fallback(self, canvas, data)

# Apply the patch
SboxgenGUI._draw_interactive_graph_fallback = patched_fallback

def main():
    print("="*60)
    print("CURVE FORCING TEST")
    print("="*60)
    print("This test FORCES different columns to make curves visible")
    print("="*60)

    root = tk.Tk()
    root.title("FORCED CURVES TEST")
    root.geometry("1200x800")

    gui = SboxgenGUI(root)
    gui.repo_path = Path.cwd() / ".workspace/rust-project"
    gui.repo_var.set(str(gui.repo_path))

    def force_render():
        print("\n[TEST] Triggering render with forced curves...")
        gui._interactive_graph_render(limit_snap=10)
        print("[TEST] Render complete - curves should be visible now!")

    root.after(1000, force_render)
    root.mainloop()

if __name__ == "__main__":
    main()