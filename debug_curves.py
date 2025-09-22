#!/usr/bin/env python3
"""Debug why curves are not showing"""

import subprocess
import json
from pathlib import Path

def debug_graph_data():
    """Check if there are edges that should render as curves"""

    # Run git-graph to get the data
    git_graph = Path.cwd() / "src/git-graph/target/release/git-graph"
    repo_path = Path.cwd() / ".workspace/rust-project"

    # Get ASCII output with column info
    result = subprocess.run(
        [str(git_graph), "-n", "30"],
        cwd=str(repo_path),
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return

    print("Git graph ASCII output:")
    print("=" * 60)
    lines = result.stdout.splitlines()[:10]
    for i, line in enumerate(lines):
        print(f"{i:2}: {line}")

    print("\n" + "=" * 60)
    print("Analysis:")

    # Count branches/merges
    branch_count = 0
    merge_count = 0

    for line in result.stdout.splitlines():
        # Look for branch indicators
        if "╭" in line or "╮" in line:
            branch_count += 1
        if "╯" in line or "╰" in line:
            merge_count += 1

    print(f"Found {branch_count} branch indicators")
    print(f"Found {merge_count} merge indicators")

    if branch_count > 0 or merge_count > 0:
        print("\n✓ The graph SHOULD have curves!")
        print("The problem is in the rendering, not the data.")
    else:
        print("\n✗ No branches/merges found in the graph")
        print("The graph is linear, so no curves are expected.")

    # Check the parsing logic
    print("\n" + "=" * 60)
    print("Checking what the GUI would see:")

    # Simulate the parsing
    nodes = []
    edges = []

    for i, line in enumerate(lines[:10]):
        # Simple node detection
        if "●" in line or "◯" in line:
            col = 0  # Simplified - would need proper parsing
            nodes.append({"idx": i, "column": col})

            # Add edge to previous
            if i > 0:
                edges.append({"from": i-1, "to": i})

    print(f"Nodes: {len(nodes)}")
    print(f"Edges: {len(edges)}")

    # Check if edges have different columns
    different_col_edges = 0
    for edge in edges:
        # In real code, we'd check actual column values
        # This is just for debugging
        if edge.get("from_col", 0) != edge.get("to_col", 0):
            different_col_edges += 1

    if different_col_edges > 0:
        print(f"✓ Found {different_col_edges} edges that should render as curves")
    else:
        print("✗ All edges are in same column (will render as straight lines)")

if __name__ == "__main__":
    debug_graph_data()