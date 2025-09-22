#!/usr/bin/env python3
"""
Check what data is actually passed to the render function
"""

import subprocess
import re
from pathlib import Path

# Run the same ASCII parsing that GUI does
def parse_like_gui():
    repo = Path.cwd() / ".workspace/rust-project"
    git_graph = Path.cwd() / "src/git-graph/target/release/git-graph"

    # Get ASCII output
    result = subprocess.run(
        [str(git_graph), "--style", "ascii", "--no-color", "-n", "10"],
        cwd=str(repo),
        capture_output=True,
        text=True
    )

    lines = result.stdout.splitlines()

    print("Step 1: Parse commits from ASCII")
    print("="*60)

    commits = []
    for ln in lines:
        m = re.search(r"\b[0-9a-fA-F]{7}\b", ln)
        if not m:
            continue

        graph_part = ln[:m.start()]
        sha = m.group(0).lower()

        # Find marker position (like GUI does)
        marker_positions = []
        for i, ch in enumerate(graph_part):
            if ch in ('*', 'o', '●', '○'):
                marker_positions.append(i)

        if marker_positions:
            pos = marker_positions[-1]
        else:
            pos = 0

        # Column calculation (from GUI code)
        if pos <= 1:
            col = 0
        else:
            col = (pos - 1) // 2

        commits.append({"short": sha, "column": col})
        print(f"  {sha}: pos={pos}, column={col} | {ln[:50]}")

    print(f"\nTotal commits parsed: {len(commits)}")

    # Get parent relationships
    print("\nStep 2: Get parent relationships")
    print("="*60)

    parents_map = {}
    result = subprocess.run(
        ["git", "rev-list", "--parents", "--topo-order", "-n", "10", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True
    )

    for ln in result.stdout.splitlines():
        parts = [x.strip().lower() for x in ln.split() if x.strip()]
        if parts:
            child = parts[0]
            parents_map[child] = parts[1:] if len(parts) > 1 else []

    for sha, parents in list(parents_map.items())[:5]:
        print(f"  {sha[:7]} -> {[p[:7] for p in parents]}")

    # Build nodes and edges
    print("\nStep 3: Build nodes and edges (GUI logic)")
    print("="*60)

    nodes = []
    parent_lists = []

    for idx, c in enumerate(commits):
        sha = c["short"]
        full_sha = None

        # Find full SHA
        for full in parents_map.keys():
            if full.startswith(sha):
                full_sha = full
                break

        if full_sha:
            parents = parents_map.get(full_sha, [])
        else:
            parents = []

        node = {
            "idx": idx,
            "id": full_sha or sha,
            "short": sha,
            "column": c["column"]
        }
        nodes.append(node)
        parent_lists.append(parents)

        print(f"  Node {idx}: {sha} (col {c['column']}) parents={[p[:7] for p in parents]}")

    # Build edges (GUI logic)
    print("\nStep 4: Build edges")
    print("="*60)

    id_to_idx = {nd["id"]: i for i, nd in enumerate(nodes)}
    edges = []

    for i, parents in enumerate(parent_lists):
        child_node = nodes[i]

        for p in parents:
            j = id_to_idx.get(p)
            if j is not None:
                parent_node = nodes[j]
                edges.append({"from": i, "to": j})

                from_col = child_node["column"]
                to_col = parent_node["column"]

                if from_col != to_col:
                    print(f"  CURVE: {child_node['short']} (col {from_col}) -> {parent_node['short']} (col {to_col})")
                else:
                    print(f"  straight: {child_node['short']} -> {parent_node['short']}")
            else:
                print(f"  WARNING: Parent {p[:7]} not in nodes!")

    print(f"\nTotal edges: {len(edges)}")

    # THE PROBLEM
    print("\n" + "="*60)
    print("THE PROBLEM:")
    print("="*60)

    # Check if branch nodes have edges
    branch_nodes = [n for n in nodes if n["column"] == 1]
    main_nodes = [n for n in nodes if n["column"] == 0]

    print(f"Branch nodes (col 1): {[n['short'] for n in branch_nodes]}")
    print(f"Main nodes (col 0): {[n['short'][:7] for n in main_nodes[:5]]}")

    # Check edges for branch nodes
    for bn in branch_nodes:
        idx = bn["idx"]
        outgoing = [e for e in edges if e["from"] == idx]
        incoming = [e for e in edges if e["to"] == idx]

        print(f"\nBranch node {bn['short']}:")
        print(f"  Outgoing edges: {outgoing}")
        print(f"  Incoming edges: {incoming}")

        if not outgoing:
            print(f"  *** NO OUTGOING EDGE - THIS IS THE PROBLEM!")

    print("\n" + "="*60)
    print("SOLUTION: Branch nodes need edges to connect to main line!")
    print("The parent of c4ae278 is c53a8aa but it's not in the nodes list")
    print("because git rev-list returns commits in a different order than git-graph")

if __name__ == "__main__":
    parse_like_gui()