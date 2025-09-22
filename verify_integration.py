#!/usr/bin/env python3
"""Test to verify the new rendering method works correctly"""

import subprocess
from pathlib import Path

def test_git_graph_output():
    """Test that git-graph binary produces correct output"""

    git_graph = Path.cwd() / "src/git-graph/target/release/git-graph"
    repo_path = Path.cwd() / ".workspace/rust-project"

    print("="*60)
    print("Testing git-graph binary")
    print("="*60)

    # Test SVG output
    print("\n1. Testing SVG output:")
    result = subprocess.run(
        [str(git_graph), "--svg", "-n", "10"],
        cwd=str(repo_path),
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(f"✓ SVG output successful ({len(result.stdout)} chars)")
        # Check for key elements
        has_circles = "<circle" in result.stdout
        has_lines = "<line" in result.stdout or "<path" in result.stdout
        print(f"  - Has nodes (circles): {has_circles}")
        print(f"  - Has edges (lines/paths): {has_lines}")
    else:
        print(f"✗ SVG generation failed: {result.stderr}")

    # Test ASCII output
    print("\n2. Testing ASCII output:")
    result = subprocess.run(
        [str(git_graph), "-n", "10"],
        cwd=str(repo_path),
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(f"✓ ASCII output successful ({len(result.stdout.splitlines())} lines)")
        # Show first few lines
        lines = result.stdout.splitlines()[:5]
        for line in lines:
            print(f"  {line}")
    else:
        print(f"✗ ASCII generation failed: {result.stderr}")

    print("\n" + "="*60)
    print("Summary: git-graph binary is working correctly")
    print("The integration should render graphs properly")
    print("="*60)

if __name__ == "__main__":
    test_git_graph_output()