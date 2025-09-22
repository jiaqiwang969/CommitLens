#!/usr/bin/env python3
"""
Direct fix by patching the data before rendering
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "tools"))

from sboxgen_gui import SboxgenGUI
import tkinter as tk

# Store original safe method
orig_safe = SboxgenGUI._draw_interactive_graph_safe

def patched_safe(self, canvas, data):
    """Patch data to add missing branch connections"""

    nodes = data.get('nodes', [])
    edges = data.get('edges', [])

    print(f"\n[PATCH] Before: {len(nodes)} nodes, {len(edges)} edges")

    # Analyze columns
    by_column = {}
    for i, node in enumerate(nodes):
        col = node.get('column', 0)
        if col not in by_column:
            by_column[col] = []
        by_column[col].append(i)

    print(f"[PATCH] Nodes by column: {list(by_column.keys())}")

    # If we have column 1 (branch), add connections
    if 1 in by_column and 0 in by_column:
        branch_nodes = by_column[1]
        main_nodes = by_column[0]

        print(f"[PATCH] Branch nodes: {branch_nodes}")
        print(f"[PATCH] Main nodes: {main_nodes[:5]}")

        # CRITICAL: Add edge from last branch node to next main node
        if branch_nodes:
            last_branch = branch_nodes[-1]

            # Find the next main node after the last branch
            next_main = None
            for main_idx in main_nodes:
                if main_idx > last_branch:
                    next_main = main_idx
                    break

            if next_main:
                # Check if edge exists
                exists = any(
                    e['from'] == last_branch and e['to'] == next_main
                    for e in edges
                )

                if not exists:
                    print(f"[PATCH] ADDING MISSING EDGE: {last_branch} -> {next_main}")
                    edges.append({
                        'from': last_branch,
                        'to': next_main,
                        'color': '#FF5722'
                    })

    # Also add edge from first branch to previous main
    if 1 in by_column and 0 in by_column:
        branch_nodes = by_column[1]
        main_nodes = by_column[0]

        if branch_nodes:
            first_branch = branch_nodes[0]

            # Find previous main node
            prev_main = None
            for main_idx in reversed(main_nodes):
                if main_idx < first_branch:
                    prev_main = main_idx
                    break

            if prev_main:
                exists = any(
                    e['from'] == prev_main and e['to'] == first_branch
                    for e in edges
                )

                if not exists:
                    print(f"[PATCH] ADDING BRANCH START: {prev_main} -> {first_branch}")
                    edges.append({
                        'from': prev_main,
                        'to': first_branch,
                        'color': '#FF5722'
                    })

    print(f"[PATCH] After: {len(nodes)} nodes, {len(edges)} edges")

    # Update data
    data['edges'] = edges

    # Call original
    return orig_safe(self, canvas, data)

# Apply patch
SboxgenGUI._draw_interactive_graph_safe = patched_safe

# Run GUI
root = tk.Tk()
root.title("PATCHED - Branch connections added")
root.geometry("1200x800")

gui = SboxgenGUI(root)
gui.repo_path = Path.cwd() / ".workspace/rust-project"
gui.repo_var.set(str(gui.repo_path))

def trigger():
    print("\n" + "="*60)
    print("TRIGGERING WITH PATCH")
    gui._interactive_graph_render(limit_snap=10)

root.after(1000, trigger)
root.mainloop()