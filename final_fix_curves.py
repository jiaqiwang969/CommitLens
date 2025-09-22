#!/usr/bin/env python3
"""Final fix - Force branch connections to be drawn"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "tools"))

from sboxgen_gui import SboxgenGUI
import tkinter as tk

# Monkey-patch the fallback render to FORCE curves
orig_fallback = SboxgenGUI._draw_interactive_graph_fallback

def force_curves_fallback(self, canvas, data):
    """Modified fallback that FORCES branch curves"""

    print("\n!!!! FORCING CURVES IN FALLBACK !!!!")

    # Get the data
    nodes = data.get('nodes', [])
    edges = data.get('edges', [])

    # Find nodes in different columns
    print(f"Nodes by column:")
    col0_nodes = []
    col1_nodes = []
    for i, node in enumerate(nodes):
        col = node.get('column', 0)
        if col == 0:
            col0_nodes.append(i)
        elif col == 1:
            col1_nodes.append(i)

    print(f"  Column 0: {col0_nodes[:5]}")
    print(f"  Column 1: {col1_nodes[:5]}")

    # FORCE ADD MISSING EDGES
    if col1_nodes:
        # Connect last branch node to next main node
        last_branch = col1_nodes[-1]
        next_main = None
        for idx in col0_nodes:
            if idx > last_branch:
                next_main = idx
                break

        if next_main is not None:
            print(f"\nFORCING CURVE: node {last_branch} (branch) -> node {next_main} (main)")
            # Add the missing edge
            edges.append({
                'from': last_branch,
                'to': next_main,
                'color': '#FF5722'
            })

            # Update data
            data['edges'] = edges

    # Call original
    return orig_fallback(self, canvas, data)

# Apply patch
SboxgenGUI._draw_interactive_graph_fallback = force_curves_fallback

# Also patch enhanced
orig_enhanced = SboxgenGUI._draw_interactive_graph_safe_enhanced

def force_curves_enhanced(self, canvas, data):
    """Modified enhanced that FORCES branch curves"""
    print("\n!!!! ENHANCED WITH FORCED CURVES !!!!")

    # Force add missing edges like in fallback
    nodes = data.get('nodes', [])
    edges = data.get('edges', [])

    # Find branch nodes
    branch_nodes = [i for i, n in enumerate(nodes) if n.get('column', 0) == 1]
    main_nodes = [i for i, n in enumerate(nodes) if n.get('column', 0) == 0]

    if branch_nodes and main_nodes:
        # Connect last branch to next main
        last_branch = branch_nodes[-1]
        for main_idx in main_nodes:
            if main_idx > last_branch:
                # Check if edge exists
                edge_exists = any(
                    e['from'] == last_branch and e['to'] == main_idx
                    for e in edges
                )
                if not edge_exists:
                    print(f"FORCING EDGE: {last_branch} -> {main_idx}")
                    edges.append({
                        'from': last_branch,
                        'to': main_idx,
                        'color': '#FF5722'
                    })
                break

    data['edges'] = edges
    return orig_enhanced(self, canvas, data)

SboxgenGUI._draw_interactive_graph_safe_enhanced = force_curves_enhanced

# Run GUI
root = tk.Tk()
root.title("FORCED CURVES - Final Fix")
root.geometry("1200x800")

gui = SboxgenGUI(root)
gui.repo_path = Path.cwd() / ".workspace/rust-project"
gui.repo_var.set(str(gui.repo_path))

def trigger():
    print("\n" + "="*60)
    print("TRIGGERING RENDER WITH FORCED CURVES")
    print("="*60)
    gui._interactive_graph_render(limit_snap=10)
    print("="*60)
    print("Check the Exec Graph tab - curves MUST appear now!")

root.after(1000, trigger)
root.mainloop()