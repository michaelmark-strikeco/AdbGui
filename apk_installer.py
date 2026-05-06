#!/usr/bin/env python3
"""APK Installer — entry point.

The implementation lives in src/. This file's only job is to pick the right
Tk root class (TkinterDnD if available, plain Tk otherwise) and start the app.
"""

import tkinter as tk

from src.dnd import HAS_DND, TkinterDnD
from src.app import APKInstaller


def main():
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
        print("Drag-and-drop disabled. Install it with:  pip install tkinterdnd2")

    APKInstaller(root)
    root.mainloop()


if __name__ == "__main__":
    main()
