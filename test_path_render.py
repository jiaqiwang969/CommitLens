#!/usr/bin/env python3
"""Test the fixed SVG path rendering"""

import tkinter as tk
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import re

def parse_svg_path(path: str) -> list:
    """Parse SVG path to coordinates"""
    coords = []
    commands = re.findall(r'[MLQ][^MLQ]*', path)

    for cmd in commands:
        parts = cmd.strip()
        cmd_type = parts[0]

        if cmd_type in ['M', 'L']:
            # Move or Line
            match = re.search(r'(\d+(?:\.\d+)?),(\d+(?:\.\d+)?)', cmd)
            if match:
                x = float(match.group(1))
                y = float(match.group(2))
                coords.extend([x, y])

        elif cmd_type == 'Q':
            # Quadratic Bezier
            # Format: Q cx,cy ex,ey
            matches = re.findall(r'(\d+(?:\.\d+)?),(\d+(?:\.\d+)?)', cmd)
            for match in matches:
                x = float(match[0])
                y = float(match[1])
                coords.extend([x, y])

    return coords

def test_path_rendering():
    """Test path rendering with real git-graph SVG"""

    # Generate SVG
    git_graph = Path.cwd() / "src/git-graph/target/release/git-graph"
    repo_path = Path.cwd() / ".workspace/rust-project"

    result = subprocess.run(
        [str(git_graph), "--svg", "-n", "50"],
        cwd=str(repo_path),
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return

    # Parse SVG
    root = ET.fromstring(result.stdout)

    # Count elements
    paths = []
    lines = []
    circles = []

    for elem in root:
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == "path":
            d = elem.get("d", "")
            stroke = elem.get("stroke", "black")
            paths.append({"d": d, "stroke": stroke})
            print(f"Found path: {d[:60]}... color={stroke}")
        elif tag == "line":
            lines.append(elem)
        elif tag == "circle":
            circles.append(elem)

    print(f"\nSummary: {len(circles)} nodes, {len(lines)} lines, {len(paths)} paths")

    # Create window to render
    window = tk.Tk()
    window.title("Path Rendering Test")
    window.geometry("800x600")

    canvas = tk.Canvas(window, bg="#2a2a2a")
    canvas.pack(fill=tk.BOTH, expand=True)

    # Color mapping
    color_map = {
        "blue": "#2196F3",
        "red": "#F44336",
        "green": "#4CAF50",
        "orange": "#FF9800",
        "purple": "#9C27B0",
        "gray": "#9E9E9E",
    }

    # Draw paths first (curves)
    for path_info in paths:
        coords = parse_svg_path(path_info["d"])
        color = color_map.get(path_info["stroke"], path_info["stroke"])

        if len(coords) >= 4:
            print(f"Drawing path with {len(coords)//2} points, color={color}")
            canvas.create_line(
                coords,
                fill=color,
                width=2,
                smooth=True,
                splinesteps=20,
                capstyle=tk.ROUND,
                tags="path"
            )

    # Draw lines
    for line in lines:
        x1 = float(line.get("x1", 0))
        y1 = float(line.get("y1", 0))
        x2 = float(line.get("x2", 0))
        y2 = float(line.get("y2", 0))
        stroke = line.get("stroke", "blue")
        color = color_map.get(stroke, stroke)

        canvas.create_line(
            x1, y1, x2, y2,
            fill=color,
            width=2,
            tags="line"
        )

    # Draw circles on top
    for circle in circles:
        cx = float(circle.get("cx", 0))
        cy = float(circle.get("cy", 0))
        r = float(circle.get("r", 4))
        fill = circle.get("fill", "blue")
        stroke = circle.get("stroke", "blue")

        fill_color = color_map.get(fill, fill)
        stroke_color = color_map.get(stroke, stroke)

        if fill == "white":
            # Merge node
            canvas.create_oval(
                cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1,
                fill="#2a2a2a",
                outline=stroke_color,
                width=2,
                tags="node"
            )
        else:
            # Regular node
            canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill=fill_color,
                outline=stroke_color,
                tags="node"
            )

    print("\nRendering complete!")
    print("You should see curves/paths if there are branches in the repository")

    window.mainloop()

if __name__ == "__main__":
    test_path_rendering()