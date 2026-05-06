"""Modal dialogs: settings (custom actions) and package picker."""

import tkinter as tk
from tkinter import filedialog
from typing import Callable

from .theme import T
from .widgets import make_button


def open_settings(app):
    """Open the Custom Actions settings dialog.

    Mutates `app.custom_actions` directly. Calls `app._save_settings()` and
    `app._rebuild_custom_buttons()` after every change so the sidebar stays
    in sync without an explicit Save button.
    """
    win = tk.Toplevel(app.root)
    win.title("Settings — Custom Actions")
    win.configure(bg=T["bg"])
    win.minsize(420, 300)
    win.grab_set()
    app.root.update_idletasks()
    win.geometry(f"520x420+{app.root.winfo_x() + 40}+{app.root.winfo_y() + 40}")

    tk.Label(win, text="Custom Actions", bg=T["bg"], fg=T["title"],
             font=("Helvetica Neue", 16, "bold"),
             pady=14, padx=20, anchor=tk.W).pack(fill=tk.X)

    tk.Frame(win, bg=T["border"], height=1).pack(fill=tk.X)

    # Scrollable list
    list_outer = tk.Frame(win, bg=T["bg"])
    list_outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

    canvas = tk.Canvas(list_outer, bg=T["bg"], highlightthickness=0)
    sb = tk.Scrollbar(list_outer, orient=tk.VERTICAL, command=canvas.yview)
    list_frame = tk.Frame(canvas, bg=T["bg"])

    list_frame.bind("<Configure>",
                    lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=list_frame, anchor=tk.NW)
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    sb.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh_list():
        for w in list_frame.winfo_children():
            w.destroy()
        if not app.custom_actions:
            tk.Label(list_frame, text="No custom actions yet.",
                     bg=T["bg"], fg=T["subtext"],
                     font=("Helvetica Neue", 11)).pack(anchor=tk.W, pady=4)
            return
        for i, action in enumerate(app.custom_actions):
            row = tk.Frame(list_frame, bg=T["surface"],
                           highlightbackground=T["border"], highlightthickness=1)
            row.pack(fill=tk.X, pady=(0, 6))
            inner = tk.Frame(row, bg=T["surface"], padx=10, pady=8)
            inner.pack(fill=tk.X)
            tk.Label(inner, text=action["name"], bg=T["surface"], fg=T["text"],
                     font=("Helvetica Neue", 12, "bold"),
                     anchor=tk.W).pack(fill=tk.X)
            tk.Label(inner, text=action["script"], bg=T["surface"], fg=T["subtext"],
                     font=("Menlo", 10), anchor=tk.W,
                     wraplength=380, justify=tk.LEFT).pack(fill=tk.X, pady=(2, 4))

            def make_delete(idx):
                def delete():
                    app.custom_actions.pop(idx)
                    app._save_settings()
                    app._rebuild_custom_buttons()
                    refresh_list()
                return delete

            make_button(inner, "✕ Remove", make_delete(i),
                        variant="secondary").pack(anchor=tk.W)

    refresh_list()

    # Add new action
    tk.Frame(win, bg=T["border"], height=1).pack(fill=tk.X)

    add_frame = tk.Frame(win, bg=T["surface"], padx=16, pady=14)
    add_frame.pack(fill=tk.X)

    tk.Label(add_frame, text="ADD ACTION", bg=T["surface"], fg=T["subtext"],
             font=("Helvetica Neue", 9)).pack(anchor=tk.W, pady=(0, 8))

    name_row = tk.Frame(add_frame, bg=T["surface"])
    name_row.pack(fill=tk.X, pady=(0, 6))
    tk.Label(name_row, text="Name", bg=T["surface"], fg=T["text"],
             font=("Helvetica Neue", 11), width=6, anchor=tk.W).pack(side=tk.LEFT)
    name_var = tk.StringVar()
    tk.Entry(name_row, textvariable=name_var,
             bg=T["raised"], fg=T["text"], insertbackground=T["text"],
             relief=tk.FLAT, font=("Helvetica Neue", 11),
             highlightbackground=T["border"], highlightthickness=1
             ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

    path_row = tk.Frame(add_frame, bg=T["surface"])
    path_row.pack(fill=tk.X, pady=(0, 10))
    tk.Label(path_row, text="Script", bg=T["surface"], fg=T["text"],
             font=("Helvetica Neue", 11), width=6, anchor=tk.W).pack(side=tk.LEFT)
    path_var = tk.StringVar()
    tk.Entry(path_row, textvariable=path_var,
             bg=T["raised"], fg=T["text"], insertbackground=T["text"],
             relief=tk.FLAT, font=("Menlo", 10),
             highlightbackground=T["border"], highlightthickness=1
             ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))

    def browse_script():
        p = filedialog.askopenfilename(
            parent=win, title="Select shell script",
            filetypes=[("Shell scripts", "*.sh"), ("All files", "*.*")])
        if p:
            path_var.set(p)

    make_button(path_row, "Browse…", browse_script,
                variant="secondary").pack(side=tk.LEFT)

    def add_action():
        name   = name_var.get().strip()
        script = path_var.get().strip()
        if not name or not script:
            return
        app.custom_actions.append({"name": name, "script": script})
        app._save_settings()
        app._rebuild_custom_buttons()
        name_var.set("")
        path_var.set("")
        refresh_list()

    make_button(add_frame, "Add Action", add_action,
                variant="custom").pack(anchor=tk.W)


def show_package_picker(parent: tk.Misc, packages: list[str],
                        on_select: Callable[[str], None]):
    """Searchable picker over `packages`. Calls `on_select(pkg)` once a choice
    is confirmed, then closes itself."""
    win = tk.Toplevel(parent)
    win.title("Select package")
    win.configure(bg=T["bg"])
    win.transient(parent)
    win.grab_set()
    parent.update_idletasks()
    win.geometry(f"460x420+{parent.winfo_x() + 60}+{parent.winfo_y() + 60}")

    # Filter
    filter_var = tk.StringVar()
    top = tk.Frame(win, bg=T["bg"], padx=14, pady=12)
    top.pack(fill=tk.X)
    tk.Label(top, text="Filter:", bg=T["bg"], fg=T["text"],
             font=("Helvetica Neue", 11)).pack(side=tk.LEFT)
    tk.Entry(top, textvariable=filter_var,
             bg=T["raised"], fg=T["text"], insertbackground=T["text"],
             relief=tk.FLAT, font=("Menlo", 11),
             highlightbackground=T["border"], highlightthickness=1,
             ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

    # Listbox
    body = tk.Frame(win, bg=T["bg"], padx=14)
    body.pack(fill=tk.BOTH, expand=True, pady=(0, 14))
    lb = tk.Listbox(body, bg=T["input"], fg=T["text"],
                    selectbackground=T["btn_install_bg"],
                    selectforeground="#ffffff",
                    font=("Menlo", 11), relief=tk.FLAT, bd=0,
                    highlightthickness=1, highlightbackground=T["border"])
    sb = tk.Scrollbar(body, command=lb.yview)
    lb.configure(yscrollcommand=sb.set)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def repopulate(*_):
        needle = filter_var.get().lower()
        lb.delete(0, tk.END)
        for p in packages:
            if needle in p.lower():
                lb.insert(tk.END, p)
    filter_var.trace_add("write", repopulate)
    repopulate()

    def choose(_=None):
        sel = lb.curselection()
        if sel:
            on_select(lb.get(sel[0]))
            win.destroy()

    lb.bind("<Double-Button-1>", choose)

    btn_row = tk.Frame(win, bg=T["bg"], padx=14)
    btn_row.pack(fill=tk.X, pady=(0, 14))
    make_button(btn_row, "Select", choose,
                variant="install").pack(side=tk.RIGHT, padx=(6, 0))
    make_button(btn_row, "Cancel", win.destroy,
                variant="secondary").pack(side=tk.RIGHT)
