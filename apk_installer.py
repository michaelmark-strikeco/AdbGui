#!/usr/bin/env python3
"""APK Installer — install APKs via adb and launch scrcpy from a GUI."""

import json
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime

SETTINGS_FILE = Path.home() / ".apk_installer_settings.json"

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False
    TkinterDnD = None

# ── Theme ─────────────────────────────────────────────────────────────────────
# Each key is a semantic role, not a palette name.
# Every bg/fg pair must have a contrast ratio ≥ 4.5:1.
T = {
    # ── Backgrounds ──────────────────────────────────────────────────────────
    "bg":          "#0d1117",   # app base
    "surface":     "#161b22",   # cards / panels
    "raised":      "#21262d",   # drop zone, slightly elevated
    "input":       "#0d1117",   # log area / combobox field
    "border":      "#30363d",

    # ── Text ─────────────────────────────────────────────────────────────────
    "text":        "#e6edf3",   # primary readable text
    "subtext":     "#8b949e",   # section labels, hints
    "title":       "#79c0ff",   # app title

    # ── All buttons use white text — backgrounds must be dark enough for ≥4.5:1 ──
    "btn2_bg":     "#3d444d",   # neutral slate  — Browse / Clear / Refresh
    "btn2_fg":     "#ffffff",
    "btn2_hover":  "#4d5460",

    "btn_install_bg":  "#1f6feb",   # blue
    "btn_install_fg":  "#ffffff",
    "btn_scrcpy_bg":   "#1a7f37",   # dark green
    "btn_scrcpy_fg":   "#ffffff",
    "btn_combo_bg":    "#9a6700",   # dark amber
    "btn_combo_fg":    "#ffffff",

    # ── Custom action buttons ─────────────────────────────────────────────────
    "btn_custom_bg":    "#6e40c9",   # purple
    "btn_custom_fg":    "#ffffff",
    "btn_custom_hover": "#7d4fd6",

    # ── Network button (Wi-Fi ADB) ────────────────────────────────────────────
    "btn_net_bg":       "#1b6e7c",   # teal
    "btn_net_fg":       "#ffffff",
    "btn_net_hover":    "#22808f",

    # ── Log tag colours ───────────────────────────────────────────────────────
    "log_success": "#3fb950",
    "log_error":   "#f85149",
    "log_info":    "#79c0ff",
    "log_warn":    "#d29922",
    "log_dim":     "#8b949e",
}


class APKInstaller:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("APK Installer")
        self.root.geometry("860x640")
        self.root.configure(bg=T["bg"])
        self.root.minsize(720, 520)

        self.selected_apk = tk.StringVar()
        self.selected_device = tk.StringVar()
        self.devices: list[str] = []
        self.custom_actions: list[dict] = self._load_settings()

        self._build_ui()
        self._refresh_devices()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=T["bg"], pady=12)
        hdr.pack(fill=tk.X, padx=24)
        tk.Label(hdr, text="APK Installer", bg=T["bg"], fg=T["title"],
                 font=("Helvetica Neue", 22, "bold")).pack(side=tk.LEFT)
        self._btn(hdr, "⚙  Settings", self._open_settings,
                  variant="secondary").pack(side=tk.RIGHT)

        # Body row
        body = tk.Frame(self.root, bg=T["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 8))

        left = tk.Frame(body, bg=T["bg"])
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        right = tk.Frame(body, bg=T["surface"],
                         highlightbackground=T["border"], highlightthickness=1,
                         width=210)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        self._build_drop_zone(left)
        self._build_file_strip(left)
        self._build_sidebar(right)
        self._build_log_panel(self.root)

    def _build_drop_zone(self, parent):
        frame = tk.Frame(parent, bg=T["raised"],
                         highlightbackground=T["border"], highlightthickness=1,
                         height=170)
        frame.pack(fill=tk.X, pady=(0, 10))
        frame.pack_propagate(False)

        inner = tk.Frame(frame, bg=T["raised"])
        inner.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        tk.Label(inner, text="📦", bg=T["raised"],
                 font=("Helvetica Neue", 38)).pack()
        hint = ("Drop APK here" if HAS_DND else "Click Browse to select APK")
        tk.Label(inner, text=hint, bg=T["raised"], fg=T["text"],
                 font=("Helvetica Neue", 13)).pack(pady=(4, 0))
        if HAS_DND:
            tk.Label(inner, text="or click Browse below", bg=T["raised"],
                     fg=T["subtext"], font=("Helvetica Neue", 11)).pack()

        if HAS_DND:
            for w in (frame, inner):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)

        self.drop_frame = frame

    def _build_file_strip(self, parent):
        frame = tk.Frame(parent, bg=T["surface"],
                         highlightbackground=T["border"], highlightthickness=1)
        frame.pack(fill=tk.X, pady=(0, 10))

        inner = tk.Frame(frame, bg=T["surface"], padx=12, pady=10)
        inner.pack(fill=tk.X)

        tk.Label(inner, text="SELECTED FILE", bg=T["surface"], fg=T["subtext"],
                 font=("Helvetica Neue", 9)).pack(anchor=tk.W)

        self.file_label = tk.Label(
            inner, textvariable=self.selected_apk,
            bg=T["surface"], fg=T["text"], font=("Menlo", 11),
            wraplength=480, justify=tk.LEFT, anchor=tk.W)
        self.file_label.pack(fill=tk.X, pady=(2, 6))

        row = tk.Frame(inner, bg=T["surface"])
        row.pack(anchor=tk.W)
        self._btn(row, "Browse…", self._browse, variant="secondary").pack(side=tk.LEFT, padx=(0, 6))
        self._btn(row, "Clear", self._clear_selection, variant="secondary").pack(side=tk.LEFT)

    def _build_sidebar(self, parent):
        pad = tk.Frame(parent, bg=T["surface"], padx=14, pady=14)
        pad.pack(fill=tk.BOTH, expand=True)

        # Devices
        tk.Label(pad, text="DEVICE", bg=T["surface"], fg=T["subtext"],
                 font=("Helvetica Neue", 9)).pack(anchor=tk.W)

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

        self.device_menu = ttk.Combobox(
            pad, textvariable=self.selected_device,
            state="readonly", font=("Menlo", 11),
            style="Dark.TCombobox", width=20)
        self.device_menu.pack(fill=tk.X, pady=(4, 2))

        self._btn(pad, "⟳  Refresh Devices", self._refresh_devices, variant="secondary").pack(fill=tk.X, pady=(4, 18))

        sep = tk.Frame(pad, bg=T["border"], height=1)
        sep.pack(fill=tk.X, pady=(0, 14))

        tk.Label(pad, text="ACTIONS", bg=T["surface"], fg=T["subtext"],
                 font=("Helvetica Neue", 9)).pack(anchor=tk.W, pady=(0, 6))

        self._btn(pad, "Install APK",      self._install_apk,        variant="install").pack(fill=tk.X, pady=(0, 6))
        self._btn(pad, "Launch scrcpy",    self._launch_scrcpy,      variant="scrcpy").pack(fill=tk.X,  pady=(0, 6))
        self._btn(pad, "Install + Launch", self._install_and_launch, variant="combo").pack(fill=tk.X,   pady=(0, 6))
        self._btn(pad, "📡  Wi-Fi ADB",    self._enable_wifi_adb,    variant="network").pack(fill=tk.X)

        # Custom action buttons (rebuilt whenever settings change)
        self.custom_sep = tk.Frame(pad, bg=T["border"], height=1)
        self.custom_frame = tk.Frame(pad, bg=T["surface"])
        self._rebuild_custom_buttons()

    def _build_log_panel(self, parent):
        frame = tk.Frame(parent, bg=T["bg"])
        frame.pack(fill=tk.X, padx=24, pady=(0, 18))

        hdr = tk.Frame(frame, bg=T["bg"])
        hdr.pack(fill=tk.X, pady=(0, 4))
        tk.Label(hdr, text="OUTPUT", bg=T["bg"], fg=T["subtext"],
                 font=("Helvetica Neue", 9)).pack(side=tk.LEFT)
        self._btn(hdr, "Clear", self._clear_log, variant="secondary", width=50).pack(side=tk.RIGHT)

        self.log = scrolledtext.ScrolledText(
            frame, height=9, bg=T["input"], fg=T["text"],
            font=("Menlo", 11), relief=tk.FLAT, bd=0,
            padx=10, pady=8, insertbackground=T["text"])
        self.log.pack(fill=tk.X)
        self.log.config(state=tk.DISABLED)
        self.log.tag_config("success", foreground=T["log_success"])
        self.log.tag_config("error",   foreground=T["log_error"])
        self.log.tag_config("info",    foreground=T["log_info"])
        self.log.tag_config("dim",     foreground=T["log_dim"])
        self.log.tag_config("warn",    foreground=T["log_warn"])

    # ── Widget factory ────────────────────────────────────────────────────────

    # variant → (bg, fg, hover_bg, font_size, pady)
    _BTN_STYLES = {
        "secondary": ("btn2_bg",        "btn2_fg",        "btn2_hover",           11, 5),
        "install":   ("btn_install_bg",  "btn_install_fg", "btn_install_bg",       12, 8),
        "scrcpy":    ("btn_scrcpy_bg",   "btn_scrcpy_fg",  "btn_scrcpy_bg",        12, 8),
        "combo":     ("btn_combo_bg",    "btn_combo_fg",   "btn_combo_bg",         12, 8),
        "custom":    ("btn_custom_bg",   "btn_custom_fg",  "btn_custom_hover",     12, 8),
        "network":   ("btn_net_bg",      "btn_net_fg",     "btn_net_hover",        12, 8),
    }

    def _btn(self, parent, text, command, variant="secondary", width=None):
        bg_key, fg_key, hover_key, fsize, pady = self._BTN_STYLES[variant]
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

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_drop(self, event):
        path = event.data.strip()
        if path.startswith("{") and path.endswith("}"):
            path = path[1:-1]
        path = path.strip("'\"")
        self._resolve_and_set(path)

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select APK",
            filetypes=[("Android Package", "*.apk"), ("All files", "*.*")])
        if path:
            self._resolve_and_set(path)

    def _clear_selection(self):
        self.selected_apk.set("")

    # ── APK resolution ────────────────────────────────────────────────────────

    def _resolve_and_set(self, raw: str):
        p = Path(raw)
        if p.is_dir():
            apk = self._latest_apk(p)
            if apk:
                self.selected_apk.set(str(apk))
                self._log(f"Directory — using newest APK: {apk.name}", "info")
            else:
                self._log(f"No .apk files found in: {p}", "error")
        elif p.suffix.lower() == ".apk" and p.exists():
            self.selected_apk.set(str(p))
            self._log(f"Selected: {p.name}", "info")
        else:
            self._log(f"Not a valid APK or directory: {p}", "error")

    @staticmethod
    def _latest_apk(directory: Path) -> Path | None:
        apks = list(directory.rglob("*.apk"))
        return max(apks, key=lambda f: f.stat().st_mtime) if apks else None

    # ── Device management ─────────────────────────────────────────────────────

    def _refresh_devices(self):
        def run():
            try:
                r = subprocess.run(["adb", "devices"],
                                   capture_output=True, text=True, timeout=5)
                lines = r.stdout.strip().splitlines()[1:]
                devs  = [l.split("\t")[0] for l in lines
                         if "\tdevice" in l]
                self.devices = devs
                self.root.after(0, self._update_device_menu)
            except FileNotFoundError:
                self.root.after(0, lambda: self._log(
                    "adb not found — is Android SDK platform-tools in PATH?", "error"))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"Refresh failed: {e}", "error"))

        threading.Thread(target=run, daemon=True).start()

    def _update_device_menu(self):
        if self.devices:
            self.device_menu["values"] = self.devices
            if self.selected_device.get() not in self.devices:
                self.selected_device.set(self.devices[0])
            self._log(f"{len(self.devices)} device(s) found: {', '.join(self.devices)}", "success")
        else:
            self.device_menu["values"] = []
            self.selected_device.set("")
            self._log("No devices connected (run: adb devices)", "warn")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _install_apk(self):
        apk = self.selected_apk.get()
        if not apk:
            self._log("No APK selected", "error")
            return
        cmd = self._adb_prefix() + ["install", "-r", apk]
        self._run_async(cmd, success_msg="✓ Install complete")

    def _launch_scrcpy(self):
        cmd = ["scrcpy"] + (["-s", self.selected_device.get()]
                             if self.selected_device.get() else [])
        self._log(f"Launching: {' '.join(cmd)}", "info")
        threading.Thread(target=lambda: subprocess.Popen(cmd), daemon=True).start()

    def _install_and_launch(self):
        apk = self.selected_apk.get()
        if not apk:
            self._log("No APK selected", "error")
            return
        cmd = self._adb_prefix() + ["install", "-r", apk]

        def run():
            if self._exec(cmd, success_msg="✓ Install complete"):
                self.root.after(0, self._launch_scrcpy)

        threading.Thread(target=run, daemon=True).start()

    def _enable_wifi_adb(self):
        """Put the device in TCP/IP mode on port 5555, then connect over LAN."""
        def run():
            ip = self._get_device_ip()
            if not ip:
                self.root.after(0, lambda: self._log(
                    "Could not detect device IP — make sure Wi-Fi is on", "error"))
                return

            if not self._exec(self._adb_prefix() + ["tcpip", "5555"],
                              success_msg="✓ ADB listening on TCP 5555"):
                return

            # adbd needs a moment to restart on the new port
            time.sleep(2)

            if self._exec(["adb", "connect", f"{ip}:5555"],
                          success_msg=f"✓ Connected over LAN: {ip}:5555"):
                self.root.after(500, self._refresh_devices)

        threading.Thread(target=run, daemon=True).start()

    def _get_device_ip(self) -> str | None:
        """Best-effort device IP lookup via `adb shell ip -4 route`."""
        try:
            r = subprocess.run(
                self._adb_prefix() + ["shell", "ip", "-4", "route"],
                capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                if " src " in line:
                    return line.split(" src ", 1)[1].split()[0]
        except Exception:
            pass
        return None

    def _adb_prefix(self) -> list[str]:
        cmd = ["adb"]
        if self.selected_device.get():
            cmd += ["-s", self.selected_device.get()]
        return cmd

    # ── Command execution ─────────────────────────────────────────────────────

    def _run_async(self, cmd: list[str], success_msg="Done"):
        threading.Thread(target=self._exec,
                         args=(cmd,), kwargs={"success_msg": success_msg},
                         daemon=True).start()

    def _exec(self, cmd: list[str], success_msg="Done") -> bool:
        self.root.after(0, lambda: self._log("$ " + " ".join(cmd), "dim"))
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.root.after(0, lambda l=line: self._log(l))
            proc.wait()
            if proc.returncode == 0:
                self.root.after(0, lambda: self._log(success_msg, "success"))
                return True
            self.root.after(0, lambda: self._log(
                f"Command exited with code {proc.returncode}", "error"))
            return False
        except FileNotFoundError:
            self.root.after(0, lambda: self._log(
                f"Not found: {cmd[0]} — is it installed?", "error"))
            return False
        except Exception as e:
            self.root.after(0, lambda: self._log(f"Error: {e}", "error"))
            return False

    # ── Custom actions ────────────────────────────────────────────────────────

    def _rebuild_custom_buttons(self):
        for w in self.custom_frame.winfo_children():
            w.destroy()
        if self.custom_actions:
            self.custom_sep.pack(fill=tk.X, pady=(14, 0))
            self.custom_frame.pack(fill=tk.X)
            tk.Label(self.custom_frame, text="CUSTOM", bg=T["surface"], fg=T["subtext"],
                     font=("Helvetica Neue", 9)).pack(anchor=tk.W, pady=(10, 6))
            for action in self.custom_actions:
                name   = action["name"]
                script = action["script"]
                self._btn(self.custom_frame, name,
                          lambda s=script, n=name: self._run_script(s, n),
                          variant="custom").pack(fill=tk.X, pady=(0, 6))
        else:
            self.custom_sep.pack_forget()
            self.custom_frame.pack_forget()

    def _run_script(self, script: str, name: str):
        path = Path(script)
        if not path.exists():
            self._log(f"Script not found: {script}", "error")
            return
        self._log(f"Running: {name}", "info")
        self._run_async(["bash", script], success_msg=f"✓ {name} complete")

    # ── Settings ──────────────────────────────────────────────────────────────

    def _load_settings(self) -> list[dict]:
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            return data.get("custom_actions", [])
        except Exception:
            return []

    def _save_settings(self):
        SETTINGS_FILE.write_text(
            json.dumps({"custom_actions": self.custom_actions}, indent=2))

    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Settings — Custom Actions")
        win.configure(bg=T["bg"])
        win.geometry("520x420")
        win.minsize(420, 300)
        win.grab_set()

        # ── Header ────────────────────────────────────────────────────────────
        tk.Label(win, text="Custom Actions", bg=T["bg"], fg=T["title"],
                 font=("Helvetica Neue", 16, "bold"),
                 pady=14, padx=20, anchor=tk.W).pack(fill=tk.X)

        tk.Frame(win, bg=T["border"], height=1).pack(fill=tk.X)

        # ── Scrollable list ───────────────────────────────────────────────────
        list_outer = tk.Frame(win, bg=T["bg"])
        list_outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        canvas = tk.Canvas(list_outer, bg=T["bg"], highlightthickness=0)
        sb = tk.Scrollbar(list_outer, orient=tk.VERTICAL, command=canvas.yview)
        list_frame = tk.Frame(canvas, bg=T["bg"])

        list_frame.bind("<Configure>",
                        lambda _: canvas.configure(
                            scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=list_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh_list():
            for w in list_frame.winfo_children():
                w.destroy()
            if not self.custom_actions:
                tk.Label(list_frame, text="No custom actions yet.",
                         bg=T["bg"], fg=T["subtext"],
                         font=("Helvetica Neue", 11)).pack(anchor=tk.W, pady=4)
                return
            for i, action in enumerate(self.custom_actions):
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
                        self.custom_actions.pop(idx)
                        self._save_settings()
                        self._rebuild_custom_buttons()
                        refresh_list()
                    return delete

                self._btn(inner, "✕ Remove", make_delete(i),
                          variant="secondary").pack(anchor=tk.W)

        refresh_list()

        # ── Add new action ────────────────────────────────────────────────────
        tk.Frame(win, bg=T["border"], height=1).pack(fill=tk.X)

        add_frame = tk.Frame(win, bg=T["surface"], padx=16, pady=14)
        add_frame.pack(fill=tk.X)

        tk.Label(add_frame, text="ADD ACTION", bg=T["surface"], fg=T["subtext"],
                 font=("Helvetica Neue", 9)).pack(anchor=tk.W, pady=(0, 8))

        # Name
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

        # Script path
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

        self._btn(path_row, "Browse…", browse_script,
                  variant="secondary").pack(side=tk.LEFT)

        def add_action():
            name   = name_var.get().strip()
            script = path_var.get().strip()
            if not name or not script:
                return
            self.custom_actions.append({"name": name, "script": script})
            self._save_settings()
            self._rebuild_custom_buttons()
            name_var.set("")
            path_var.set("")
            refresh_list()

        self._btn(add_frame, "Add Action", add_action,
                  variant="custom").pack(anchor=tk.W)

    # ── Log helpers ───────────────────────────────────────────────────────────

    def _log(self, msg: str, tag: str | None = None):
        self.log.config(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.insert(tk.END, f"[{ts}]  {msg}\n", tag or "")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _clear_log(self):
        self.log.config(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.config(state=tk.DISABLED)


# ── Entry point ───────────────────────────────────────────────────────────────

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
