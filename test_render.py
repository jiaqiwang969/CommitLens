#!/usr/bin/env python3
"""Test the new git-graph rendering integration"""

import tkinter as tk
from pathlib import Path
import sys
import os

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).parent / "tools"))

from sboxgen_gui import SboxgenGUI

def test_render():
    """Test the new rendering function"""

    # Create root window
    root = tk.Tk()
    root.title("Git Graph Render Test")
    root.geometry("1200x800")

    # Create GUI instance
    gui = SboxgenGUI(root)
    # gui.pack(fill=tk.BOTH, expand=True)  # SboxgenGUI is already packed inside __init__

    # Set repo path to the rust project
    gui.repo_path = Path.cwd() / ".workspace/rust-project"

    # Test rendering
    try:
        print("Testing interactive graph render...")
        gui._interactive_graph_render(limit_snap=50)
        print("Render completed successfully!")

        # Check if hitboxes were created
        if hasattr(gui, '_igraph_hitboxes') and gui._igraph_hitboxes:
            print(f"Created {len(gui._igraph_hitboxes)} hitboxes")
        else:
            print("Warning: No hitboxes created")

    except Exception as e:
        print(f"Error during render: {e}")
        import traceback
        traceback.print_exc()

    # Start the main loop
    root.mainloop()

if __name__ == "__main__":
    test_render()