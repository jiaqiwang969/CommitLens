#!/usr/bin/env python3
"""Direct test - Draw curves manually to prove it works"""

import tkinter as tk

def test_curves_directly():
    """Draw curves directly on canvas to prove Tkinter can do it"""

    root = tk.Tk()
    root.title("DIRECT CURVE TEST - Should see RED CURVES")
    root.geometry("600x400")
    root.configure(bg="black")

    canvas = tk.Canvas(root, bg="#2a2a2a", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    # Draw some nodes
    nodes = [
        (100, 50, 0),   # x, y, column
        (100, 100, 0),
        (200, 150, 1),  # Branch node
        (200, 200, 1),  # Branch node
        (100, 250, 0),
        (100, 300, 0),
    ]

    # Draw straight lines first
    canvas.create_line(100, 50, 100, 100, fill="white", width=2)
    canvas.create_line(200, 150, 200, 200, fill="white", width=2)
    canvas.create_line(100, 250, 100, 300, fill="white", width=2)

    # NOW DRAW CURVES - THE MISSING CONNECTIONS
    print("\nDrawing curves:")

    # Curve 1: From main to branch (100,100) -> (200,150)
    points = []
    for t in range(21):
        t = t / 20
        x = 100 + t * 100
        y = 100 + t * 50
        points.extend([x, y])

    canvas.create_line(points, fill="red", width=3, smooth=True, tags="curve1")
    print("Drew curve 1: main -> branch")

    # Curve 2: From branch back to main (200,200) -> (100,250)
    points = []
    for t in range(21):
        t = t / 20
        x = 200 - t * 100
        y = 200 + t * 50
        points.extend([x, y])

    canvas.create_line(points, fill="red", width=3, smooth=True, tags="curve2")
    print("Drew curve 2: branch -> main")

    # Draw nodes on top
    for x, y, col in nodes:
        r = 6
        color = "#4CAF50" if col == 0 else "#2196F3"
        canvas.create_oval(x-r, y-r, x+r, y+r, fill=color, outline="white", width=2)

    # Labels
    canvas.create_text(100, 30, text="Main", fill="white", font=("Arial", 12, "bold"))
    canvas.create_text(200, 130, text="Branch", fill="white", font=("Arial", 12, "bold"))
    canvas.create_text(300, 200, text="← RED CURVES", fill="red", font=("Arial", 14, "bold"))

    # Debug: count canvas items
    items = canvas.find_all()
    print(f"\nCanvas has {len(items)} items")
    for tag in ["curve1", "curve2"]:
        items_with_tag = canvas.find_withtag(tag)
        print(f"  Items with tag '{tag}': {len(items_with_tag)}")

    root.mainloop()

if __name__ == "__main__":
    test_curves_directly()