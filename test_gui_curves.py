#!/usr/bin/env python3
"""Final test to verify the curve rendering in GUI works correctly"""

import tkinter as tk
from pathlib import Path
import sys

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent / "tools"))

from sboxgen_gui import SboxgenGUI

def test_gui_with_curves():
    """Test the GUI with the new curve rendering"""

    print("="*60)
    print("Testing GUI with Curve Rendering")
    print("="*60)

    # Create root window
    root = tk.Tk()
    root.title("Git Graph with Curves - Final Test")
    root.geometry("1200x800")

    # Create GUI instance
    gui = SboxgenGUI(root)

    # Set repo path to the rust project
    gui.repo_path = Path.cwd() / ".workspace/rust-project"
    gui.repo_var.set(str(gui.repo_path))

    # Create test controls
    def test_render():
        print("\nTriggering render with curve support...")
        try:
            # Force a render
            gui._interactive_graph_render(limit_snap=50)

            print("Render triggered successfully!")
            print("The graph should now show:")
            print("  - Nodes (circles) for commits")
            print("  - Lines for direct parent-child relationships")
            print("  - CURVES for branch/merge relationships")

            # Check if render was successful
            if hasattr(gui, '_igraph_hitboxes') and gui._igraph_hitboxes:
                print(f"✓ Created {len(gui._igraph_hitboxes)} clickable areas")

        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()

    # Add delay to allow GUI to initialize
    root.after(500, test_render)

    # Add manual trigger button
    def add_controls():
        # Find the exec graph tab
        for widget in gui.winfo_children():
            if hasattr(widget, 'winfo_class') and widget.winfo_class() == 'TNotebook':
                # Switch to exec graph tab
                widget.select(1)  # Usually the second tab
                break

        # Add info label
        info_label = tk.Label(
            gui,
            text="Look for CURVED lines connecting branches (red/gray colors)",
            bg="#2a2a2a",
            fg="#FFD700",
            font=("Arial", 12, "bold")
        )
        info_label.pack(side=tk.TOP, pady=10)

        # Add refresh button
        refresh_btn = tk.Button(
            gui,
            text="Re-render with Curves",
            command=test_render,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 10, "bold")
        )
        refresh_btn.pack(side=tk.TOP, pady=5)

    root.after(1000, add_controls)

    print("\nGUI launched!")
    print("Check the 'Exec Graph' tab")
    print("You should see:")
    print("  1. Blue nodes for main branch commits")
    print("  2. Red/gray nodes for feature branch commits")
    print("  3. CURVED lines showing branch/merge relationships")
    print("  4. White circles for merge commits")

    root.mainloop()

if __name__ == "__main__":
    test_gui_with_curves()