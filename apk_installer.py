#!/usr/bin/env python3
"""APK Installer — install APKs via adb and launch scrcpy from a GUI."""

import json
import re
import signal
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime

ROOT_DIR        = Path(__file__).resolve().parent
SETTINGS_FILE   = ROOT_DIR / ".apk_installer_settings.json"
CAPTURES_DIR    = ROOT_DIR / "captures"
REMOTE_REC_PATH = "/sdcard/_adbgui_rec.mp4"
RECENT_LIMIT    = 10

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

    "btn_close_bg":     "#8b3a3a",   # muted red — destructive / stop
    "btn_close_fg":     "#ffffff",
    "btn_close_hover":  "#a04a4a",

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

        settings = self._load_settings()
        self.custom_actions: list[dict] = settings.get("custom_actions", [])
        self.recent_apks:    list[str]  = settings.get("recent_apks", [])

        self.recording_proc: subprocess.Popen | None = None
        self.logcat_win = None

        self._build_ui()
        self._refresh_devices()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self._setup_ttk_style()
        # Header
        hdr = tk.Frame(self.root, bg=T["bg"], pady=12)
        hdr.pack(fill=tk.X, padx=24)
        tk.Label(hdr, text="APK Installer", bg=T["bg"], fg=T["title"],
                 font=("Helvetica Neue", 22, "bold")).pack(side=tk.LEFT)
        self._btn(hdr, "⚙  Settings", self._open_settings,
                  variant="secondary").pack(side=tk.RIGHT)
        self._btn(hdr, "🪵  Logcat", self._open_logcat,
                  variant="secondary").pack(side=tk.RIGHT, padx=(0, 8))

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
        self._build_uninstall_panel(left)
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

        # Recent APKs dropdown — only shown when the list is non-empty
        self.recent_var  = tk.StringVar()
        self.recent_menu = ttk.Combobox(
            inner, textvariable=self.recent_var,
            state="readonly", font=("Menlo", 10),
            style="Dark.TCombobox")
        self.recent_menu.bind("<<ComboboxSelected>>",
                              lambda _: self._on_recent_picked())
        self._refresh_recent_menu()

    def _build_uninstall_panel(self, parent):
        frame = tk.Frame(parent, bg=T["surface"],
                         highlightbackground=T["border"], highlightthickness=1)
        frame.pack(fill=tk.X, pady=(0, 10))

        inner = tk.Frame(frame, bg=T["surface"], padx=12, pady=10)
        inner.pack(fill=tk.X)

        tk.Label(inner, text="UNINSTALL APP", bg=T["surface"], fg=T["subtext"],
                 font=("Helvetica Neue", 9)).pack(anchor=tk.W)

        self.uninstall_var = tk.StringVar()
        entry = tk.Entry(inner, textvariable=self.uninstall_var,
                         bg=T["raised"], fg=T["text"], insertbackground=T["text"],
                         relief=tk.FLAT, font=("Menlo", 11),
                         highlightbackground=T["border"], highlightthickness=1)
        entry.pack(fill=tk.X, pady=(4, 6))

        row = tk.Frame(inner, bg=T["surface"])
        row.pack(anchor=tk.W)
        self._btn(row, "Pick from device…", self._pick_package,
                  variant="secondary").pack(side=tk.LEFT, padx=(0, 6))
        self._btn(row, "Uninstall", self._uninstall_package,
                  variant="close").pack(side=tk.LEFT)

    def _setup_ttk_style(self):
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

    def _build_sidebar(self, parent):
        pad = tk.Frame(parent, bg=T["surface"], padx=14, pady=14)
        pad.pack(fill=tk.BOTH, expand=True)

        # Devices
        tk.Label(pad, text="DEVICE", bg=T["surface"], fg=T["subtext"],
                 font=("Helvetica Neue", 9)).pack(anchor=tk.W)

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

        self.wifi_btn = self._btn(pad, "📡  Wi-Fi ADB",    self._enable_wifi_adb,
                                  variant="network")
        self.wifi_btn.pack(fill=tk.X)

        # Visible only when the selected device is TCP-connected (IP:port serial)
        self.close_btn = self._btn(pad, "🔌  Close Wi-Fi ADB", self._close_wifi_adb,
                                   variant="close")
        self.selected_device.trace_add("write", lambda *_: self._update_close_btn())

        # Capture section
        tk.Frame(pad, bg=T["border"], height=1).pack(fill=tk.X, pady=(14, 0))
        tk.Label(pad, text="CAPTURE", bg=T["surface"], fg=T["subtext"],
                 font=("Helvetica Neue", 9)).pack(anchor=tk.W, pady=(10, 6))

        self._btn(pad, "📸  Screenshot", self._take_screenshot,
                  variant="secondary").pack(fill=tk.X, pady=(0, 6))
        self.record_btn = self._btn(pad, "🔴  Record Screen", self._toggle_recording,
                                    variant="close")
        self.record_btn.pack(fill=tk.X)

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
        "close":     ("btn_close_bg",    "btn_close_fg",   "btn_close_hover",      12, 8),
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

        def run():
            if self._exec(cmd, success_msg="✓ Install complete"):
                self.root.after(0, lambda: self._add_recent(apk))
        threading.Thread(target=run, daemon=True).start()

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
                self.root.after(0, lambda: self._add_recent(apk))
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

    def _close_wifi_adb(self):
        """Switch a TCP-connected device back to USB mode and disconnect."""
        dev = self.selected_device.get()
        if not self._is_tcp_device(dev):
            self._log("Selected device is not on TCP/IP", "error")
            return

        def run():
            self._exec(["adb", "-s", dev, "usb"],
                       success_msg="✓ Device switched back to USB mode")
            self._exec(["adb", "disconnect", dev],
                       success_msg=f"✓ Disconnected {dev}")
            self.root.after(500, self._refresh_devices)

        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def _is_tcp_device(serial: str) -> bool:
        """A TCP serial looks like '192.168.x.y:5555'. USB serials never contain ':'."""
        if ":" not in serial:
            return False
        host = serial.rsplit(":", 1)[0]
        return host.count(".") == 3

    def _update_close_btn(self):
        if self._is_tcp_device(self.selected_device.get()):
            self.close_btn.pack(fill=tk.X, pady=(6, 0), after=self.wifi_btn)
        else:
            self.close_btn.pack_forget()

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

    # ── Recent APKs ───────────────────────────────────────────────────────────

    def _add_recent(self, apk: str):
        if apk in self.recent_apks:
            self.recent_apks.remove(apk)
        self.recent_apks.insert(0, apk)
        del self.recent_apks[RECENT_LIMIT:]
        self._save_settings()
        self._refresh_recent_menu()

    def _refresh_recent_menu(self):
        # Drop entries whose files no longer exist
        self.recent_apks[:] = [p for p in self.recent_apks if Path(p).exists()]
        if not self.recent_apks:
            self.recent_menu.pack_forget()
            return
        self.recent_menu["values"] = self.recent_apks
        self.recent_menu.pack(fill=tk.X, pady=(8, 0))

    def _on_recent_picked(self):
        path = self.recent_var.get()
        if path:
            self._resolve_and_set(path)
            self.recent_var.set("")  # don't keep it stuck on the dropdown

    # ── Uninstall ─────────────────────────────────────────────────────────────

    def _uninstall_package(self):
        pkg = self.uninstall_var.get().strip()
        if not pkg:
            self._log("Enter a package name to uninstall", "error")
            return
        self._run_async(self._adb_prefix() + ["uninstall", pkg],
                        success_msg=f"✓ Uninstalled {pkg}")

    def _pick_package(self):
        """Fetch installed packages and let the user pick one."""
        def run():
            try:
                r = subprocess.run(
                    self._adb_prefix() + ["shell", "pm", "list", "packages"],
                    capture_output=True, text=True, timeout=10)
                pkgs = sorted(
                    line.removeprefix("package:").strip()
                    for line in r.stdout.splitlines()
                    if line.startswith("package:"))
                if not pkgs:
                    self.root.after(0, lambda: self._log(
                        "No packages found on device", "warn"))
                    return
                self.root.after(0, lambda: self._show_package_picker(pkgs))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"pm list failed: {e}", "error"))
        threading.Thread(target=run, daemon=True).start()

    def _show_package_picker(self, packages: list[str]):
        win = tk.Toplevel(self.root)
        win.title("Select package")
        win.configure(bg=T["bg"])
        win.geometry("460x420")
        win.transient(self.root)
        win.grab_set()

        # Filter box
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
                self.uninstall_var.set(lb.get(sel[0]))
                win.destroy()

        lb.bind("<Double-Button-1>", choose)

        btn_row = tk.Frame(win, bg=T["bg"], padx=14)
        btn_row.pack(fill=tk.X, pady=(0, 14))
        self._btn(btn_row, "Select", choose,
                  variant="install").pack(side=tk.RIGHT, padx=(6, 0))
        self._btn(btn_row, "Cancel", win.destroy,
                  variant="secondary").pack(side=tk.RIGHT)

    # ── Capture: screenshot & screen record ───────────────────────────────────

    def _take_screenshot(self):
        CAPTURES_DIR.mkdir(exist_ok=True)
        out_path = CAPTURES_DIR / f"screen_{datetime.now():%Y%m%d_%H%M%S}.png"

        def run():
            self.root.after(0, lambda: self._log("Taking screenshot…", "info"))
            try:
                with open(out_path, "wb") as f:
                    proc = subprocess.run(
                        self._adb_prefix() + ["exec-out", "screencap", "-p"],
                        stdout=f, stderr=subprocess.PIPE, timeout=20)
                if proc.returncode == 0 and out_path.stat().st_size > 0:
                    self.root.after(0, lambda: self._log(
                        f"✓ Saved {out_path.relative_to(ROOT_DIR)}", "success"))
                else:
                    out_path.unlink(missing_ok=True)
                    self.root.after(0, lambda: self._log(
                        "Screenshot failed (empty output)", "error"))
            except Exception as e:
                out_path.unlink(missing_ok=True)
                self.root.after(0, lambda: self._log(f"Screenshot error: {e}", "error"))
        threading.Thread(target=run, daemon=True).start()

    def _toggle_recording(self):
        if self.recording_proc is None:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        try:
            self.recording_proc = subprocess.Popen(
                self._adb_prefix() + ["shell", "screenrecord", REMOTE_REC_PATH])
            self.record_btn.config(text="⏹  Stop Recording")
            self._log("● Recording — max 3 min on Android", "info")
        except Exception as e:
            self._log(f"Failed to start recording: {e}", "error")
            self.recording_proc = None

    def _stop_recording(self):
        proc = self.recording_proc
        self.recording_proc = None
        self.record_btn.config(text="🔴  Record Screen")

        def run():
            try:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=4)
            except Exception:
                # Belt-and-braces: kill on device, then locally
                subprocess.run(self._adb_prefix() + ["shell", "killall", "-2", "screenrecord"],
                               capture_output=True, timeout=5)
                try: proc.wait(timeout=3)
                except Exception: proc.kill()

            time.sleep(1)  # let the device finalise the mp4
            CAPTURES_DIR.mkdir(exist_ok=True)
            local = CAPTURES_DIR / f"rec_{datetime.now():%Y%m%d_%H%M%S}.mp4"
            ok = self._exec(self._adb_prefix() + ["pull", REMOTE_REC_PATH, str(local)],
                            success_msg=f"✓ Saved {local.relative_to(ROOT_DIR)}")
            if ok:
                subprocess.run(self._adb_prefix() + ["shell", "rm", REMOTE_REC_PATH],
                               capture_output=True, timeout=5)
        threading.Thread(target=run, daemon=True).start()

    # ── Logcat viewer ─────────────────────────────────────────────────────────

    def _open_logcat(self):
        if self.logcat_win is not None and self.logcat_win.winfo_exists():
            self.logcat_win.lift()
            return
        LogcatViewer(self)

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

    def _load_settings(self) -> dict:
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            # Back-compat: older versions wrote a bare list under no key
            if isinstance(data, list):
                return {"custom_actions": data, "recent_apks": []}
            return data
        except Exception:
            return {}

    def _save_settings(self):
        SETTINGS_FILE.write_text(json.dumps({
            "custom_actions": self.custom_actions,
            "recent_apks":    self.recent_apks,
        }, indent=2))

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


# ── Logcat viewer ─────────────────────────────────────────────────────────────

# logcat -v time line:  "MM-DD hh:mm:ss.SSS L/Tag(  pid): message"
LOGCAT_LINE_RE = re.compile(r"^\d{2}-\d{2} [\d:.]+ +([VDIWEF])/")


class LogcatViewer:
    LEVELS = ["V", "D", "I", "W", "E"]   # default I = noise floor most people want

    def __init__(self, app: "APKInstaller"):
        self.app = app
        self.proc: subprocess.Popen | None = None
        self.reader_thread: threading.Thread | None = None

        win = tk.Toplevel(app.root)
        app.logcat_win = win
        self.win = win
        win.title("Logcat")
        win.configure(bg=T["bg"])
        win.geometry("980x620")
        win.minsize(720, 400)
        win.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build(win)

    def _build(self, win: tk.Toplevel):
        # ── Filter bar ───────────────────────────────────────────────────────
        bar = tk.Frame(win, bg=T["bg"], padx=12, pady=10)
        bar.pack(fill=tk.X)

        def lbl(parent, text):
            return tk.Label(parent, text=text, bg=T["bg"], fg=T["subtext"],
                            font=("Helvetica Neue", 10))

        # Package
        lbl(bar, "Package:").pack(side=tk.LEFT)
        self.pkg_var = tk.StringVar()
        tk.Entry(bar, textvariable=self.pkg_var, width=22,
                 bg=T["raised"], fg=T["text"], insertbackground=T["text"],
                 relief=tk.FLAT, font=("Menlo", 11),
                 highlightbackground=T["border"], highlightthickness=1
                 ).pack(side=tk.LEFT, padx=(6, 12))

        # Level
        lbl(bar, "Level:").pack(side=tk.LEFT)
        self.level_var = tk.StringVar(value="I")
        ttk.Combobox(bar, textvariable=self.level_var, values=self.LEVELS,
                     state="readonly", style="Dark.TCombobox", width=4,
                     font=("Menlo", 11)).pack(side=tk.LEFT, padx=(6, 12))

        # Filter text
        lbl(bar, "Filter:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        tk.Entry(bar, textvariable=self.filter_var, width=22,
                 bg=T["raised"], fg=T["text"], insertbackground=T["text"],
                 relief=tk.FLAT, font=("Menlo", 11),
                 highlightbackground=T["border"], highlightthickness=1
                 ).pack(side=tk.LEFT, padx=(6, 12))

        self.autoscroll_var = tk.BooleanVar(value=True)
        tk.Checkbutton(bar, text="auto-scroll", variable=self.autoscroll_var,
                       bg=T["bg"], fg=T["text"], selectcolor=T["raised"],
                       activebackground=T["bg"], activeforeground=T["text"],
                       font=("Helvetica Neue", 10), bd=0
                       ).pack(side=tk.LEFT)

        # ── Action buttons ───────────────────────────────────────────────────
        actions = tk.Frame(win, bg=T["bg"], padx=12)
        actions.pack(fill=tk.X, pady=(0, 10))

        self.start_btn = self.app._btn(actions, "▶ Start", self.start, variant="install")
        self.start_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_btn  = self.app._btn(actions, "⏹ Stop", self.stop, variant="close")
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.app._btn(actions, "Clear", self.clear,
                      variant="secondary").pack(side=tk.LEFT)

        self.status_label = tk.Label(actions, text="idle",
                                     bg=T["bg"], fg=T["subtext"],
                                     font=("Menlo", 10))
        self.status_label.pack(side=tk.RIGHT)

        # ── Output ───────────────────────────────────────────────────────────
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

        # Resolve package → pid (best effort)
        pkg = self.pkg_var.get().strip()
        pid_arg: list[str] = []
        if pkg:
            try:
                r = subprocess.run(
                    self.app._adb_prefix() + ["shell", "pidof", pkg],
                    capture_output=True, text=True, timeout=5)
                pid = r.stdout.strip().split()
                if pid:
                    pid_arg = ["--pid=" + pid[0]]
                else:
                    self._set_status(f"{pkg} not running — showing all", T["log_warn"])
            except Exception:
                pass

        cmd = self.app._adb_prefix() + ["logcat", "-v", "time",
                                        f"*:{self.level_var.get()}"] + pid_arg
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1)
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

    def _read_loop(self):
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        for raw in proc.stdout:
            if proc is not self.proc:   # superseded by another start
                return
            line = raw.rstrip("\n")
            self.win.after(0, lambda l=line: self._append(l))
        # Process ended
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
