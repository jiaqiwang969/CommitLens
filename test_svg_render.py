#!/usr/bin/env python3
"""Simple test of the new git-graph SVG rendering"""

import tkinter as tk
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

def test_svg_render():
    """Test SVG rendering directly"""

    # Generate SVG from git-graph
    repo_path = Path.cwd() / ".workspace/rust-project"
    git_graph_bin = Path.cwd() / "src/git-graph/target/release/git-graph"

    result = subprocess.run(
        [str(git_graph_bin), "--svg", "-n", "20"],
        cwd=str(repo_path),
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return

    svg_content = result.stdout
    print(f"Generated SVG with {len(svg_content)} chars")

    # Parse SVG
    try:
        root = ET.fromstring(svg_content)

        # Count elements
        lines = 0
        circles = 0
        paths = 0

        for elem in root:
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag == "line":
                lines += 1
            elif tag == "circle":
                circles += 1
            elif tag == "path":
                paths += 1

        print(f"SVG contains: {circles} nodes, {lines} lines, {paths} paths")

        # Create simple Tkinter window to render
        window = tk.Tk()
        window.title("SVG Render Test")
        window.geometry("800x600")

        canvas = tk.Canvas(window, bg="#2a2a2a")
        canvas.pack(fill=tk.BOTH, expand=True)

        # Render elements
        for elem in root:
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

            if tag == "circle":
                cx = float(elem.get("cx", 0))
                cy = float(elem.get("cy", 0))
                r = float(elem.get("r", 4))
                fill = elem.get("fill", "blue")

                # Map colors
                color_map = {
                    "blue": "#2196F3",
                    "red": "#F44336",
                    "green": "#4CAF50",
                    "orange": "#FF9800",
                }
                color = color_map.get(fill, fill)

                canvas.create_oval(
                    cx - r, cy - r, cx + r, cy + r,
                    fill=color,
                    outline=color,
                    tags="node"
                )

            elif tag == "line":
                x1 = float(elem.get("x1", 0))
                y1 = float(elem.get("y1", 0))
                x2 = float(elem.get("x2", 0))
                y2 = float(elem.get("y2", 0))
                stroke = elem.get("stroke", "blue")

                color_map = {
                    "blue": "#2196F3",
                    "red": "#F44336",
                    "green": "#4CAF50",
                    "orange": "#FF9800",
                }
                color = color_map.get(stroke, stroke)

                canvas.create_line(
                    x1, y1, x2, y2,
                    fill=color,
                    width=2,
                    tags="edge"
                )

        print("Rendering complete!")

        # Add click handler
        def on_click(event):
            x = canvas.canvasx(event.x)
            y = canvas.canvasy(event.y)
            print(f"Click at ({x:.1f}, {y:.1f})")

            # Find closest item
            item = canvas.find_closest(x, y)[0]
            tags = canvas.gettags(item)
            if "node" in tags:
                print("  -> Clicked on a node")

        canvas.bind("<Button-1>", on_click)

        window.mainloop()

    except ET.ParseError as e:
        print(f"Failed to parse SVG: {e}")

if __name__ == "__main__":
    test_svg_render()