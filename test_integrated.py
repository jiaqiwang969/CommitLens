#!/usr/bin/env python3
"""Test the integrated rendering in sboxgen_gui"""

import tkinter as tk
from pathlib import Path
import sys

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent / "tools"))

def test_integrated():
    from sboxgen_gui import SboxgenGUI

    # Create test window
    root = tk.Tk()
    root.title("Integrated Render Test")
    root.geometry("1200x800")

    # Initialize GUI
    gui = SboxgenGUI(root)

    # Override repo path
    gui.repo_path = Path.cwd() / ".workspace/rust-project"
    gui.repo_var.set(str(gui.repo_path))

    # Add test buttons to the existing notebook
    def add_test_controls():
        # Switch to Exec Graph tab
        for i, tab_name in enumerate(gui.notebook.tabs()):
            tab_text = gui.notebook.tab(tab_name, "text")
            if "Exec Graph" in tab_text:
                gui.notebook.select(i)
                break

        # Add test controls
        test_frame = tk.Frame(gui.exec_graph_tab, bg="#2a2a2a")
        test_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

        tk.Button(
            test_frame,
            text="Test Render (30 commits)",
            command=lambda: trigger_render(30),
            bg="#4CAF50",
            fg="white"
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            test_frame,
            text="Test Render (50 commits)",
            command=lambda: trigger_render(50),
            bg="#2196F3",
            fg="white"
        ).pack(side=tk.LEFT, padx=5)

    def trigger_render(limit=30):
        print("\n" + "="*60)
        print(f"Triggering interactive render with {limit} commits...")
        try:
            gui._interactive_graph_render(limit_snap=limit)
            print("Render completed successfully!")

            # Check results
            if hasattr(gui, '_igraph_hitboxes'):
                print(f"Hitboxes created: {len(gui._igraph_hitboxes)}")
            else:
                print("No hitboxes created")

            if hasattr(gui, '_igraph_nodes_xy'):
                print(f"Nodes created: {len(gui._igraph_nodes_xy)}")
            else:
                print("No nodes created")

        except Exception as e:
            print(f"Render failed: {e}")
            import traceback
            traceback.print_exc()

    # Add test controls after GUI is initialized
    root.after(100, add_test_controls)

    print("GUI initialized. Click 'Test Render' to test the new rendering.")
    print("The graph should appear in the Exec Graph tab.")

    root.mainloop()

if __name__ == "__main__":
    test_integrated()