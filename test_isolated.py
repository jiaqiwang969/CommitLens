#!/usr/bin/env python3
"""Isolated test of interactive graph rendering with curves"""

import tkinter as tk
import subprocess
from pathlib import Path
import re

def parse_ascii_graph(repo_path, limit=10):
    """Parse git-graph ASCII output to extract nodes and edges"""

    # Run git-graph
    git_graph = Path.cwd() / "src/git-graph/target/release/git-graph"
    result = subprocess.run(
        [str(git_graph), "-n", str(limit)],
        cwd=str(repo_path),
        capture_output=True,
        text=True
    )

    lines = result.stdout.splitlines()
    commits = []

    print("\nParsing ASCII output:")
    print("="*60)

    for i, line in enumerate(lines[:10]):
        # Find commit SHA
        m = re.search(r"\b[0-9a-fA-F]{7}\b", line)
        if not m:
            continue

        sha = m.group(0)
        graph_part = line[:m.start()]

        # Find commit marker position
        marker_pos = -1
        for j, ch in enumerate(graph_part):
            if ch in ('●', '○', '*', 'o'):
                marker_pos = j
                # Don't break - we want the LAST marker

        # Calculate column
        if marker_pos >= 0:
            # CORRECTED: Use actual position, considering git-graph spacing
            # In "●    b4e1b9f", marker is at pos 0, column should be 0
            # In "│ ●  888e070", marker is at pos 2, column should be 1
            column = marker_pos // 2
        else:
            column = 0

        print(f"Line {i}: marker at pos {marker_pos}, column={column} | {line[:50]}")

        # Extract subject
        subject = line[m.end():].strip()
        # Remove branch info
        if '(' in subject:
            paren_end = subject.find(')')
            if paren_end > 0:
                subject = subject[paren_end+1:].strip()

        commits.append({
            'idx': len(commits),
            'sha': sha,
            'column': column,
            'subject': subject[:50] if subject else ""
        })

    # Create edges (simple parent-child for now)
    edges = []
    for i in range(len(commits) - 1):
        edges.append({
            'from': i,
            'to': i + 1,
            'from_col': commits[i]['column'],
            'to_col': commits[i + 1]['column']
        })

    return commits, edges

def draw_graph_with_curves(canvas, commits, edges):
    """Draw the graph with curves for branch/merge"""

    canvas.delete('all')

    # Layout parameters
    y_step = 30
    x_step = 50  # Spacing between columns
    x_offset = 50
    y_offset = 30

    print("\nDrawing graph:")
    print("="*60)

    # Draw edges first
    for edge in edges:
        from_idx = edge['from']
        to_idx = edge['to']
        from_col = edge['from_col']
        to_col = edge['to_col']

        x1 = x_offset + from_col * x_step
        y1 = y_offset + from_idx * y_step
        x2 = x_offset + to_col * x_step
        y2 = y_offset + to_idx * y_step

        if from_col == to_col:
            # Same column - straight line
            print(f"Drawing straight line: ({x1},{y1}) -> ({x2},{y2})")
            canvas.create_line(
                x1, y1, x2, y2,
                fill="#2196F3",
                width=2,
                tags="edge"
            )
        else:
            # Different columns - DRAW CURVE!
            print(f"Drawing CURVE: col {from_col} -> col {to_col}, ({x1},{y1}) -> ({x2},{y2})")

            # Create bezier curve points
            points = []

            # Control points for smooth S-curve
            ctrl1_x = x1
            ctrl1_y = y1 + (y2 - y1) * 0.3
            ctrl2_x = x2
            ctrl2_y = y2 - (y2 - y1) * 0.3

            # Generate curve points
            steps = 20
            for i in range(steps + 1):
                t = i / steps
                # Cubic bezier formula
                px = (1-t)**3 * x1 + 3*(1-t)**2*t * ctrl1_x + 3*(1-t)*t**2 * ctrl2_x + t**3 * x2
                py = (1-t)**3 * y1 + 3*(1-t)**2*t * ctrl1_y + 3*(1-t)*t**2 * ctrl2_y + t**3 * y2
                points.extend([px, py])

            # Draw the curve
            canvas.create_line(
                points,
                fill="#FF5722",  # Red for curves
                width=3,
                smooth=True,
                splinesteps=10,
                tags="curve"
            )

    # Draw nodes on top
    for commit in commits:
        x = x_offset + commit['column'] * x_step
        y = y_offset + commit['idx'] * y_step

        # Node circle
        r = 6
        canvas.create_oval(
            x-r, y-r, x+r, y+r,
            fill="#2196F3" if commit['column'] == 0 else "#4CAF50",
            outline="white",
            width=2,
            tags="node"
        )

        # Label
        canvas.create_text(
            x + 15, y,
            anchor="w",
            text=f"{commit['sha']} {commit['subject']}",
            fill="white",
            font=("Monaco", 10)
        )

    print(f"\nTotal: {len(commits)} nodes, {len(edges)} edges")
    curve_count = sum(1 for e in edges if e['from_col'] != e['to_col'])
    print(f"Curves drawn: {curve_count}")

def main():
    print("="*60)
    print("ISOLATED CURVE RENDERING TEST")
    print("="*60)

    # Create window
    root = tk.Tk()
    root.title("Curve Test - Isolated")
    root.geometry("800x600")
    root.configure(bg="#1e1e1e")

    # Create canvas
    canvas = tk.Canvas(root, bg="#2a2a2a", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    # Parse and draw
    repo_path = Path.cwd() / ".workspace/rust-project"
    commits, edges = parse_ascii_graph(repo_path, 10)

    # Add delay to ensure canvas is ready
    root.after(100, lambda: draw_graph_with_curves(canvas, commits, edges))

    # Info label
    info = tk.Label(
        root,
        text="Red lines = CURVES (different columns) | Blue lines = straight (same column)",
        bg="#1e1e1e",
        fg="#FFD700",
        font=("Arial", 12, "bold")
    )
    info.pack(side=tk.BOTTOM, pady=10)

    root.mainloop()

if __name__ == "__main__":
    main()