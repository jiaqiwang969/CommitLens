#!/usr/bin/env python3
"""Test curves with a repository that has branches"""

import tkinter as tk
from pathlib import Path
import sys
import shutil

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent / "tools"))

from sboxgen_gui import SboxgenGUI

def test_with_curves():
    """Test GUI with a branched repository"""

    # Copy test repo to workspace
    test_repo = Path("/tmp/test-curves")
    workspace_repo = Path.cwd() / ".workspace/test-curves"

    if test_repo.exists():
        print(f"Using test repository with branches at: {test_repo}")
        # Copy to workspace
        if workspace_repo.exists():
            shutil.rmtree(workspace_repo)
        shutil.copytree(test_repo, workspace_repo)
    else:
        print("Creating test repository...")
        # Create it here if needed

    # Create GUI
    root = tk.Tk()
    root.title("Git Graph with Curves - TEST")
    root.geometry("1200x800")

    gui = SboxgenGUI(root)

    # Override to use test repo
    gui.repo_path = workspace_repo
    gui.repo_var.set(str(workspace_repo))

    # Override the project name
    gui.task_project_name_var.set("test-curves")

    print("\n" + "="*60)
    print("IMPORTANT: Testing with branched repository")
    print("="*60)
    print("This test repo has:")
    print("  - Main branch with commits")
    print("  - Feature branch that diverges")
    print("  - Merge commit joining branches")
    print("\nYou SHOULD see CURVED lines at:")
    print("  1. Branch point (where feature diverges)")
    print("  2. Merge point (where branches join)")
    print("="*60)

    def force_render():
        """Force a render with debug output"""
        print("\nForcing render with curves...")
        try:
            gui._interactive_graph_render(limit_snap=10)
            print("Render complete! Check the Exec Graph tab.")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

    # Auto-render after GUI loads
    root.after(1000, force_render)

    # Add manual render button
    def add_button():
        btn = tk.Button(
            gui,
            text="Force Render with Curves",
            command=force_render,
            bg="#FF5722",
            fg="white",
            font=("Arial", 12, "bold")
        )
        btn.pack(side=tk.TOP, pady=10)

    root.after(500, add_button)

    root.mainloop()

if __name__ == "__main__":
    test_with_curves()