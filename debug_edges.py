#!/usr/bin/env python3
"""Debug: Check if edges are being created correctly"""

import subprocess
import re
from pathlib import Path

def check_edges():
    """Check if edges are created with correct columns"""

    # Get git-graph output
    repo = Path.cwd() / ".workspace/rust-project"
    git_graph = Path.cwd() / "src/git-graph/target/release/git-graph"

    # Get ASCII output
    result = subprocess.run(
        [str(git_graph), "-n", "10"],
        cwd=str(repo),
        capture_output=True,
        text=True
    )

    print("Git-graph ASCII output:")
    print("="*60)
    lines = result.stdout.splitlines()

    commits = []
    for i, line in enumerate(lines[:10]):
        print(f"{i}: {line}")

        # Parse commit
        m = re.search(r"\b[0-9a-fA-F]{7}\b", line)
        if m:
            sha = m.group(0)
            graph_part = line[:m.start()]

            # Find marker position
            pos = -1
            for j, ch in enumerate(graph_part):
                if ch in ('●', '○', '*', 'o'):
                    pos = j

            # Calculate column
            if pos <= 1:
                col = 0
            else:
                col = (pos - 1) // 2

            commits.append({
                'idx': len(commits),
                'sha': sha,
                'column': col,
                'line': i
            })
            print(f"  -> SHA: {sha}, pos={pos}, column={col}")

    print("\n" + "="*60)
    print("Commits parsed:")
    for c in commits:
        print(f"  {c['idx']}: {c['sha']} at column {c['column']}")

    # Get parent relationships using git
    print("\n" + "="*60)
    print("Parent relationships:")

    result = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "10", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True
    )

    parent_map = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if parts:
            commit = parts[0][:7]
            parents = [p[:7] for p in parts[1:]]
            parent_map[commit] = parents
            print(f"  {commit} <- {parents}")

    # Build edges
    print("\n" + "="*60)
    print("Edges that should be created:")

    commit_map = {c['sha']: c for c in commits}
    edges = []

    for commit in commits:
        sha = commit['sha']
        if sha in parent_map:
            for parent_sha in parent_map[sha]:
                if parent_sha in commit_map:
                    parent = commit_map[parent_sha]
                    edge = {
                        'from': commit['idx'],
                        'to': parent['idx'],
                        'from_col': commit['column'],
                        'to_col': parent['column']
                    }
                    edges.append(edge)

                    if edge['from_col'] != edge['to_col']:
                        print(f"  CURVE: {sha} (col {edge['from_col']}) -> {parent_sha} (col {edge['to_col']})")
                    else:
                        print(f"  straight: {sha} (col {edge['from_col']}) -> {parent_sha} (col {edge['to_col']})")

    print(f"\nTotal edges: {len(edges)}")
    curve_count = sum(1 for e in edges if e['from_col'] != e['to_col'])
    print(f"Curves needed: {curve_count}")

if __name__ == "__main__":
    check_edges()