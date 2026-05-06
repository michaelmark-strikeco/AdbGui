"""Logcat viewer — separate Toplevel window with filters and live streaming."""

import re
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from .theme import T
from .adb import adb_prefix, resolve_pid
from .widgets import make_button

# logcat -v time line:  "MM-DD hh:mm:ss.SSS L/Tag(  pid): message"
LOGCAT_LINE_RE = re.compile(r"^\d{2}-\d{2} [\d:.]+ +([VDIWEF])/")


class LogcatViewer:
    LEVELS = ["V", "D", "I", "W", "E"]

    def __init__(self, app):
        """`app` is the APKInstaller — used for `app.root` and `app.selected_device`."""
        self.app = app
        self.proc: subprocess.Popen | None = None
        self.reader_thread: threading.Thread | None = None

        win = tk.Toplevel(app.root)
        app.logcat_win = win
        self.win = win
        win.title("Logcat")
        win.configure(bg=T["bg"])
        win.minsize(720, 400)
        win.protocol("WM_DELETE_WINDOW", self._on_close)

        # Place on the same monitor as the main window — without an explicit
        # +x+y the WM often drops the Toplevel onto the primary display.
        app.root.update_idletasks()
        x = app.root.winfo_x() + 40
        y = app.root.winfo_y() + 40
        win.geometry(f"980x620+{x}+{y}")

        self._build(win)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build(self, win: tk.Toplevel):
        # Filter bar
        bar = tk.Frame(win, bg=T["bg"], padx=12, pady=10)
        bar.pack(fill=tk.X)

        def lbl(parent, text):
            return tk.Label(parent, text=text, bg=T["bg"], fg=T["subtext"],
                            font=("Helvetica Neue", 10))

        history = self.app.logcat_history

        lbl(bar, "Package:").pack(side=tk.LEFT)
        self.pkg_var = tk.StringVar()
        self.pkg_combo = ttk.Combobox(
            bar, textvariable=self.pkg_var, width=22,
            values=history.get("package", []),
            style="Dark.TCombobox", font=("Menlo", 11))
        self.pkg_combo.pack(side=tk.LEFT, padx=(6, 12))

        lbl(bar, "Level:").pack(side=tk.LEFT)
        self.level_var = tk.StringVar(value="I")
        ttk.Combobox(bar, textvariable=self.level_var, values=self.LEVELS,
                     state="readonly", style="Dark.TCombobox", width=4,
                     font=("Menlo", 11)).pack(side=tk.LEFT, padx=(6, 12))

        lbl(bar, "Filter:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        self.filter_combo = ttk.Combobox(
            bar, textvariable=self.filter_var, width=22,
            values=history.get("filter", []),
            style="Dark.TCombobox", font=("Menlo", 11))
        self.filter_combo.pack(side=tk.LEFT, padx=(6, 12))

        self.autoscroll_var = tk.BooleanVar(value=True)
        tk.Checkbutton(bar, text="auto-scroll", variable=self.autoscroll_var,
                       bg=T["bg"], fg=T["text"], selectcolor=T["raised"],
                       activebackground=T["bg"], activeforeground=T["text"],
                       font=("Helvetica Neue", 10), bd=0
                       ).pack(side=tk.LEFT)

        # Action row
        actions = tk.Frame(win, bg=T["bg"], padx=12)
        actions.pack(fill=tk.X, pady=(0, 10))

        make_button(actions, "▶ Start", self.start, variant="install"
                    ).pack(side=tk.LEFT, padx=(0, 6))
        make_button(actions, "⏹ Stop",  self.stop,  variant="close"
                    ).pack(side=tk.LEFT, padx=(0, 6))
        make_button(actions, "Clear",   self.clear, variant="secondary"
                    ).pack(side=tk.LEFT)

        self.status_label = tk.Label(actions, text="idle",
                                     bg=T["bg"], fg=T["subtext"],
                                     font=("Menlo", 10))
        self.status_label.pack(side=tk.RIGHT)

        # Output
        body = tk.Frame(win, bg=T["bg"], padx=12)
        body.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        self.text = scrolledtext.ScrolledText(
            body, bg=T["input"], fg=T["text"],
            font=("Menlo", 10), relief=tk.FLAT, bd=0,
            padx=8, pady=6, insertbackground=T["text"], wrap=tk.NONE)
        self.text.pack(fill=tk.BOTH, expand=True)
        self.text.config(state=tk.DISABLED)
        self.text.tag_config("V", foreground=T["log_dim"])
        self.text.tag_config("D", foreground=T["log_info"])
        self.text.tag_config("I", foreground=T["text"])
        self.text.tag_config("W", foreground=T["log_warn"])
        self.text.tag_config("E", foreground=T["log_error"])
        self.text.tag_config("F", foreground=T["log_error"])

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        if self.proc is not None:
            return
        device = self.app.selected_device.get()
        if not device:
            self._set_status("no device selected", T["log_error"])
            return

        # Persist non-empty filter values to history before they're applied
        pkg = self.pkg_var.get().strip()
        filter_text = self.filter_var.get().strip()
        if pkg or filter_text:
            self.app._push_logcat_history(pkg, filter_text)
            history = self.app.logcat_history
            self.pkg_combo["values"]    = history.get("package", [])
            self.filter_combo["values"] = history.get("filter", [])

        # Resolve package → pid (best effort)
        pid_arg: list[str] = []
        if pkg:
            pid = resolve_pid(device, pkg)
            if pid:
                pid_arg = [f"--pid={pid}"]
            else:
                self._set_status(f"{pkg} not running — showing all", T["log_warn"])

        cmd = adb_prefix(device) + ["logcat", "-v", "time",
                                    f"*:{self.level_var.get()}"] + pid_arg
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace", bufsize=1)
        except FileNotFoundError:
            self._set_status("adb not found", T["log_error"])
            return

        self._set_status(f"streaming  ({device})", T["log_success"])
        self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.reader_thread.start()

    def stop(self):
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except Exception:
            try: self.proc.kill()
            except Exception: pass
        self.proc = None
        self._set_status("stopped", T["subtext"])

    def clear(self):
        self.text.config(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.config(state=tk.DISABLED)

    # ── Reader thread ─────────────────────────────────────────────────────────

    def _read_loop(self):
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        for raw in proc.stdout:
            if proc is not self.proc:   # superseded by another start
                return
            line = raw.rstrip("\n")
            self.win.after(0, lambda l=line: self._append(l))
        self.win.after(0, lambda: self._set_status("stopped", T["subtext"]))

    def _append(self, line: str):
        needle = self.filter_var.get().strip().lower()
        if needle and needle not in line.lower():
            return
        m = LOGCAT_LINE_RE.match(line)
        tag = m.group(1) if m else ""
        self.text.config(state=tk.NORMAL)
        self.text.insert(tk.END, line + "\n", tag)
        # Cap buffer at ~5000 lines so memory doesn't run away
        line_count = int(self.text.index("end-1c").split(".")[0])
        if line_count > 5000:
            self.text.delete("1.0", f"{line_count - 5000}.0")
        if self.autoscroll_var.get():
            self.text.see(tk.END)
        self.text.config(state=tk.DISABLED)

    def _set_status(self, text: str, color: str):
        self.status_label.config(text=text, fg=color)

    def _on_close(self):
        self.stop()
        self.app.logcat_win = None
        self.win.destroy()
