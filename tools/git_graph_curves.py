#!/usr/bin/env python3
"""
Direct curve integration for git-graph visualization
This module provides a simple way to add curves to the GUI
"""

import tkinter as tk
from typing import List, Tuple, Dict, Any

def draw_git_curves(canvas: tk.Canvas, nodes: List[Dict], edges: List[Dict]):
    """
    Draw git graph with curves for branch/merge relationships

    Args:
        canvas: Tkinter canvas to draw on
        nodes: List of node dictionaries with 'id', 'column', etc.
        edges: List of edge dictionaries with 'from', 'to', 'type', etc.
    """

    # Clear canvas
    canvas.delete('all')

    if not nodes:
        return

    # Layout parameters
    y_step = 28
    x_step = 15
    x_offset = 15
    y_offset = 24

    # Color mapping
    colors = {
        0: "#2196F3",  # Blue
        1: "#F44336",  # Red
        2: "#4CAF50",  # Green
        3: "#FF9800",  # Orange
        4: "#9C27B0",  # Purple
        5: "#00BCD4",  # Cyan
    }

    # Create node position map (倒序显示)
    n = len(nodes)
    node_positions = {}
    for i, node in enumerate(nodes):
        node_id = node.get('id', i)
        col = node.get('column', 0)
        x = x_offset + col * x_step
        y = y_offset + (n - 1 - i) * y_step  # 倒序
        node_positions[node_id] = (x, y, col)

    # Draw edges with curves
    for edge in edges:
        from_id = edge.get('from')
        to_id = edge.get('to')

        if from_id not in node_positions or to_id not in node_positions:
            continue

        x1, y1, col1 = node_positions[from_id]
        x2, y2, col2 = node_positions[to_id]

        # Determine edge type and color
        edge_type = edge.get('type', 'direct')
        color = colors.get(min(col1, col2) % len(colors), "#2196F3")

        if col1 == col2:
            # Same column - straight line
            canvas.create_line(
                x1, y1, x2, y2,
                fill=color,
                width=2,
                capstyle=tk.ROUND,
                tags="edge"
            )
        else:
            # Different columns - draw bezier curve
            # Calculate control points for smooth curve
            mid_y = (y1 + y2) / 2

            if abs(col1 - col2) == 1 and abs(y1 - y2) == y_step:
                # Adjacent columns, single step - simple curve
                ctrl_x = (x1 + x2) / 2
                ctrl_y = mid_y

                # Draw as smooth curve using multiple segments
                points = []
                for t in range(11):
                    t = t / 10.0
                    # Quadratic bezier formula
                    px = (1-t)**2 * x1 + 2*(1-t)*t * ctrl_x + t**2 * x2
                    py = (1-t)**2 * y1 + 2*(1-t)*t * ctrl_y + t**2 * y2
                    points.extend([px, py])

                canvas.create_line(
                    points,
                    fill=color,
                    width=2,
                    smooth=True,
                    splinesteps=10,
                    capstyle=tk.ROUND,
                    tags="edge"
                )
            else:
                # Multi-column span or merge - create S-curve
                # First curve from source column
                ctrl1_x = x1
                ctrl1_y = y1 + (y2 - y1) * 0.25
                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2

                # Second curve to target column
                ctrl2_x = x2
                ctrl2_y = y2 - (y2 - y1) * 0.25

                # Create smooth S-curve path
                points = []
                # First half of S-curve
                for t in range(6):
                    t = t / 10.0
                    px = (1-t)**2 * x1 + 2*(1-t)*t * ctrl1_x + t**2 * mid_x
                    py = (1-t)**2 * y1 + 2*(1-t)*t * ctrl1_y + t**2 * mid_y
                    points.extend([px, py])

                # Second half of S-curve
                for t in range(5, 11):
                    t = t / 10.0
                    px = (1-t)**2 * mid_x + 2*(1-t)*t * ctrl2_x + t**2 * x2
                    py = (1-t)**2 * mid_y + 2*(1-t)*t * ctrl2_y + t**2 * y2
                    points.extend([px, py])

                canvas.create_line(
                    points,
                    fill=color,
                    width=2,
                    smooth=True,
                    splinesteps=10,
                    capstyle=tk.ROUND,
                    tags="edge"
                )

    # Draw nodes on top
    for node in nodes:
        node_id = node.get('id', '')
        x, y, col = node_positions.get(node_id, (0, 0, 0))

        # Node appearance
        r = 5
        color = colors.get(col % len(colors), "#2196F3")
        is_merge = len(node.get('parents', [])) > 1

        if is_merge:
            # Merge commit - hollow circle
            canvas.create_oval(
                x-r-1, y-r-1, x+r+1, y+r+1,
                fill="#2a2a2a",
                outline=color,
                width=2,
                tags="node"
            )
        else:
            # Regular commit - filled circle
            canvas.create_oval(
                x-r, y-r, x+r, y+r,
                fill=color,
                outline=color,
                tags="node"
            )


def patch_gui_with_curves(gui_instance):
    """
    Patch an existing GUI instance to use curve rendering

    Args:
        gui_instance: SboxgenGUI instance to patch
    """

    # Store original method
    original_draw = gui_instance._draw_interactive_graph_fallback

    def new_draw_with_curves(canvas: tk.Canvas, data: dict):
        """Enhanced draw method with curves"""

        nodes = data.get('nodes', [])
        edges = data.get('edges', [])

        if not edges:
            # Generate edges from parent relationships
            edges = []
            for i, node in enumerate(nodes):
                node_id = node.get('id', i)
                parents = node.get('parents', [])

                for parent_id in parents:
                    # Find parent index
                    parent_idx = None
                    for j, pnode in enumerate(nodes):
                        if pnode.get('id') == parent_id:
                            parent_idx = j
                            break

                    if parent_idx is not None:
                        edge_type = 'merge' if len(parents) > 1 else 'direct'
                        edges.append({
                            'from': parent_idx,
                            'to': i,
                            'type': edge_type
                        })

        # Draw with curves
        draw_git_curves(canvas, nodes, edges)

        # Set up interaction (preserve original functionality)
        if hasattr(gui_instance, '_setup_graph_events'):
            gui_instance._setup_graph_events(canvas)

    # Replace the method
    gui_instance._draw_interactive_graph_fallback = new_draw_with_curves
    print("[PATCH] Successfully patched GUI with curve rendering")

    return gui_instance