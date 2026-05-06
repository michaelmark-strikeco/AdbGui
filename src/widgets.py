"""Reusable widget factories shared across the app."""

import tkinter as tk
from tkinter import ttk

from .theme import T, BTN_STYLES


def setup_ttk_style():
    """Configure the ttk style we use for every Combobox in the app.

    Must be called once after the root window exists, before any styled
    Combobox is created.
    """
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Dark.TCombobox",
                    fieldbackground=T["input"], background=T["raised"],
                    foreground=T["text"], selectbackground=T["btn_install_bg"],
                    selectforeground="#ffffff",
                    bordercolor=T["border"], arrowcolor=T["text"])
    style.map("Dark.TCombobox",
              fieldbackground=[("readonly", T["input"])],
              background=[("active", T["raised"])])


def make_button(parent, text, command, variant="secondary", width=None):
    """A `tk.Label` styled as a button.

    macOS forces native Aqua appearance on `tk.Button`, which loses the colour
    scheme on focus loss. Labels respect their bg/fg unconditionally, so we
    simulate clicks via bindings.
    """
    bg_key, fg_key, hover_key, fsize, pady = BTN_STYLES[variant]
    bg, fg, hover = T[bg_key], T[fg_key], T[hover_key]
    bold = variant != "secondary"
    lbl = tk.Label(
        parent, text=text,
        bg=bg, fg=fg,
        font=("Helvetica Neue", fsize, "bold" if bold else "normal"),
        cursor="hand2", pady=pady, padx=10,
        **({"width": width} if width else {}),
    )
    lbl.bind("<Enter>",    lambda _: lbl.config(bg=hover))
    lbl.bind("<Leave>",    lambda _: lbl.config(bg=bg))
    lbl.bind("<Button-1>", lambda _: command())
    return lbl
