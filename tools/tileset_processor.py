"""Launch the standalone Tk tileset processor."""

import tkinter as tk

from src.core.tileset_processor import App


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
