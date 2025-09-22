#!/usr/bin/env python3
"""Direct test to ensure curves are rendered"""

import subprocess
from pathlib import Path

# Check what git-graph outputs
git_graph = Path.cwd() / "src/git-graph/target/release/git-graph"
repo = Path.cwd() / ".workspace/rust-project"

print("Testing git-graph output:")
print("="*60)

# ASCII output
result = subprocess.run(
    [str(git_graph), "-n", "10"],
    cwd=str(repo),
    capture_output=True,
    text=True
)

print("ASCII Output:")
for i, line in enumerate(result.stdout.splitlines()[:10]):
    # Find column positions
    col_positions = []
    for j, char in enumerate(line):
        if char in "●○":
            col_positions.append(j)
    print(f"Line {i}: col={col_positions} | {line}")

print("\n" + "="*60)
print("SVG Output:")

# SVG output
result = subprocess.run(
    [str(git_graph), "--svg", "-n", "10"],
    cwd=str(repo),
    capture_output=True,
    text=True
)

# Count path elements (curves)
path_count = result.stdout.count("<path")
line_count = result.stdout.count("<line")
circle_count = result.stdout.count("<circle")

print(f"SVG contains:")
print(f"  - {circle_count} circles (nodes)")
print(f"  - {line_count} lines (straight edges)")
print(f"  - {path_count} paths (CURVES)")

if path_count > 0:
    print("\n✓ SVG has curves! The problem is in the GUI rendering.")
    # Extract path elements
    import re
    paths = re.findall(r'<path[^>]+>', result.stdout)
    for i, path in enumerate(paths[:3]):
        print(f"\nPath {i+1}: {path[:100]}...")
else:
    print("\n✗ No curves in SVG output")

print("\n" + "="*60)
print("Diagnosis:")

# Check column parsing
lines = result.stdout.splitlines()
has_different_columns = False

for line in lines:
    if "│" in line or "├" in line or "┘" in line:
        has_different_columns = True
        break

if has_different_columns:
    print("✓ Graph has branches (different columns)")
    print("The GUI should parse columns correctly from ASCII")
else:
    print("✗ Graph appears linear (same column)")

# Debug column extraction
print("\nColumn extraction test:")
ascii_lines = subprocess.run(
    [str(git_graph), "-n", "5"],
    cwd=str(repo),
    capture_output=True,
    text=True
).stdout.splitlines()

for i, line in enumerate(ascii_lines[:5]):
    # Find the rightmost commit marker
    pos = -1
    for j in range(len(line)-1, -1, -1):
        if line[j] in "●○*o":
            pos = j
            break
    if pos >= 0:
        col = pos // 2  # This is how GUI calculates it
        print(f"  Line {i}: marker at pos {pos}, column={col}")