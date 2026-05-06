"""Main application window — APKInstaller."""

import signal
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from datetime import datetime
from pathlib import Path

from .theme import (
    T, ROOT_DIR, CAPTURES_DIR, REMOTE_REC_PATH, RECENT_LIMIT,
)
from .widgets import make_button, setup_ttk_style
from .adb import (
    adb_prefix as _adb_prefix_for,
    list_devices as adb_list_devices,
    list_packages as adb_list_packages,
    get_device_ip,
    is_tcp_device,
)
from .settings import load_settings, save_settings
from .dialogs import open_settings as open_settings_dialog, show_package_picker
from .logcat import LogcatViewer
from .dnd import HAS_DND, DND_FILES


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

        s = load_settings()
        self.custom_actions: list[dict] = s.get("custom_actions", [])
        self.recent_apks:    list[str]  = s.get("recent_apks", [])
        self.logcat_history: dict       = s.get("logcat_history",
                                                {"package": [], "filter": []})

        self.recording_proc: subprocess.Popen | None = None
        self.logcat_win = None

        self._build_ui()
        self._refresh_devices()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        setup_ttk_style()

        # Header
        hdr = tk.Frame(self.root, bg=T["bg"], pady=12)
        hdr.pack(fill=tk.X, padx=24)
        tk.Label(hdr, text="APK Installer", bg=T["bg"], fg=T["title"],
                 font=("Helvetica Neue", 22, "bold")).pack(side=tk.LEFT)
        make_button(hdr, "⚙  Settings", self._open_settings,
                    variant="secondary").pack(side=tk.RIGHT)
        make_button(hdr, "🪵  Logcat", self._open_logcat,
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
        hint = "Drop APK here" if HAS_DND else "Click Browse to select APK"
        tk.Label(inner, text=hint, bg=T["raised"], fg=T["text"],
                 font=("Helvetica Neue", 13)).pack(pady=(4, 0))
        if HAS_DND:
            tk.Label(inner, text="or click Browse below", bg=T["raised"],
                     fg=T["subtext"], font=("Helvetica Neue", 11)).pack()
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
        make_button(row, "Browse…", self._browse,
                    variant="secondary").pack(side=tk.LEFT, padx=(0, 6))
        make_button(row, "Clear", self._clear_selection,
                    variant="secondary").pack(side=tk.LEFT)

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
        tk.Entry(inner, textvariable=self.uninstall_var,
                 bg=T["raised"], fg=T["text"], insertbackground=T["text"],
                 relief=tk.FLAT, font=("Menlo", 11),
                 highlightbackground=T["border"], highlightthickness=1
                 ).pack(fill=tk.X, pady=(4, 6))

        row = tk.Frame(inner, bg=T["surface"])
        row.pack(anchor=tk.W)
        make_button(row, "Pick from device…", self._pick_package,
                    variant="secondary").pack(side=tk.LEFT, padx=(0, 6))
        make_button(row, "Uninstall", self._uninstall_package,
                    variant="close").pack(side=tk.LEFT)

    def _build_sidebar(self, parent):
        # Scrollable container — once button list outgrows the viewport
        # (many custom actions), the user can wheel through it.
        canvas = tk.Canvas(parent, bg=T["surface"], highlightthickness=0)
        sb = tk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        pad = tk.Frame(canvas, bg=T["surface"], padx=14, pady=14)
        pad_window = canvas.create_window((0, 0), window=pad, anchor=tk.NW)

        # Keep scrollregion in sync with content height,
        # and stretch the inner frame to match canvas width.
        pad.bind("<Configure>",
                 lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(pad_window, width=e.width))

        # Mousewheel scrolling — only active while pointer is over the sidebar
        def on_wheel(event):
            if event.num == 4:                      # Linux scroll up
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:                    # Linux scroll down
                canvas.yview_scroll(1, "units")
            else:                                   # macOS / Windows
                canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

        def bind_wheel(_):
            canvas.bind_all("<MouseWheel>", on_wheel)
            canvas.bind_all("<Button-4>", on_wheel)
            canvas.bind_all("<Button-5>", on_wheel)

        def unbind_wheel(_):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", bind_wheel)
        canvas.bind("<Leave>", unbind_wheel)

        tk.Label(pad, text="DEVICE", bg=T["surface"], fg=T["subtext"],
                 font=("Helvetica Neue", 9)).pack(anchor=tk.W)

        self.device_menu = ttk.Combobox(
            pad, textvariable=self.selected_device,
            state="readonly", font=("Menlo", 11),
            style="Dark.TCombobox", width=20)
        self.device_menu.pack(fill=tk.X, pady=(4, 2))

        make_button(pad, "⟳  Refresh Devices", self._refresh_devices,
                    variant="secondary").pack(fill=tk.X, pady=(4, 18))

        tk.Frame(pad, bg=T["border"], height=1).pack(fill=tk.X, pady=(0, 14))

        tk.Label(pad, text="ACTIONS", bg=T["surface"], fg=T["subtext"],
                 font=("Helvetica Neue", 9)).pack(anchor=tk.W, pady=(0, 6))

        make_button(pad, "Install APK",      self._install_apk,
                    variant="install").pack(fill=tk.X, pady=(0, 6))
        make_button(pad, "Launch scrcpy",    self._launch_scrcpy,
                    variant="scrcpy").pack(fill=tk.X,  pady=(0, 6))
        make_button(pad, "Install + Launch", self._install_and_launch,
                    variant="combo").pack(fill=tk.X,   pady=(0, 6))

        self.wifi_btn = make_button(pad, "📡  Wi-Fi ADB", self._enable_wifi_adb,
                                    variant="network")
        self.wifi_btn.pack(fill=tk.X)

        self.close_btn = make_button(pad, "🔌  Close Wi-Fi ADB", self._close_wifi_adb,
                                     variant="close")
        self.selected_device.trace_add("write", lambda *_: self._update_close_btn())

        # Capture
        tk.Frame(pad, bg=T["border"], height=1).pack(fill=tk.X, pady=(14, 0))
        tk.Label(pad, text="CAPTURE", bg=T["surface"], fg=T["subtext"],
                 font=("Helvetica Neue", 9)).pack(anchor=tk.W, pady=(10, 6))

        make_button(pad, "📸  Screenshot", self._take_screenshot,
                    variant="secondary").pack(fill=tk.X, pady=(0, 6))
        self.record_btn = make_button(pad, "🔴  Record Screen", self._toggle_recording,
                                      variant="close")
        self.record_btn.pack(fill=tk.X)

        # Custom actions (rebuilt whenever settings change)
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
        make_button(hdr, "Clear", self._clear_log,
                    variant="secondary", width=50).pack(side=tk.RIGHT)

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

    # ── DND / file picker ─────────────────────────────────────────────────────

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

    # ── Devices ───────────────────────────────────────────────────────────────

    def _refresh_devices(self):
        def run():
            try:
                self.devices = adb_list_devices()
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
            self._log(f"{len(self.devices)} device(s) found: {', '.join(self.devices)}",
                      "success")
        else:
            self.device_menu["values"] = []
            self.selected_device.set("")
            self._log("No devices connected (run: adb devices)", "warn")

    def _adb_prefix(self) -> list[str]:
        return _adb_prefix_for(self.selected_device.get())

    # ── Install / scrcpy ──────────────────────────────────────────────────────

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
        # Pin scrcpy's window to the same screen as the main app
        self.root.update_idletasks()
        x = self.root.winfo_x() + 60
        y = self.root.winfo_y() + 60
        cmd = ["scrcpy", f"--window-x={x}", f"--window-y={y}"]
        if self.selected_device.get():
            cmd += ["-s", self.selected_device.get()]
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

    # ── Wi-Fi ADB ─────────────────────────────────────────────────────────────

    def _enable_wifi_adb(self):
        def run():
            ip = get_device_ip(self.selected_device.get())
            if not ip:
                self.root.after(0, lambda: self._log(
                    "Could not detect device IP — make sure Wi-Fi is on", "error"))
                return
            if not self._exec(self._adb_prefix() + ["tcpip", "5555"],
                              success_msg="✓ ADB listening on TCP 5555"):
                return
            time.sleep(2)  # adbd needs a moment to restart on the new port
            if self._exec(["adb", "connect", f"{ip}:5555"],
                          success_msg=f"✓ Connected over LAN: {ip}:5555"):
                self.root.after(500, self._refresh_devices)
        threading.Thread(target=run, daemon=True).start()

    def _close_wifi_adb(self):
        dev = self.selected_device.get()
        if not is_tcp_device(dev):
            self._log("Selected device is not on TCP/IP", "error")
            return

        def run():
            self._exec(["adb", "-s", dev, "usb"],
                       success_msg="✓ Device switched back to USB mode")
            self._exec(["adb", "disconnect", dev],
                       success_msg=f"✓ Disconnected {dev}")
            self.root.after(500, self._refresh_devices)
        threading.Thread(target=run, daemon=True).start()

    def _update_close_btn(self):
        if is_tcp_device(self.selected_device.get()):
            self.close_btn.pack(fill=tk.X, pady=(6, 0), after=self.wifi_btn)
        else:
            self.close_btn.pack_forget()

    # ── Recent APKs ───────────────────────────────────────────────────────────

    def _add_recent(self, apk: str):
        if apk in self.recent_apks:
            self.recent_apks.remove(apk)
        self.recent_apks.insert(0, apk)
        del self.recent_apks[RECENT_LIMIT:]
        self._save_settings()
        self._refresh_recent_menu()

    def _refresh_recent_menu(self):
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
            self.recent_var.set("")

    # ── Uninstall ─────────────────────────────────────────────────────────────

    def _uninstall_package(self):
        pkg = self.uninstall_var.get().strip()
        if not pkg:
            self._log("Enter a package name to uninstall", "error")
            return
        self._run_async(self._adb_prefix() + ["uninstall", pkg],
                        success_msg=f"✓ Uninstalled {pkg}")

    def _pick_package(self):
        def run():
            try:
                pkgs = adb_list_packages(self.selected_device.get())
            except Exception as e:
                self.root.after(0, lambda: self._log(f"pm list failed: {e}", "error"))
                return
            if not pkgs:
                self.root.after(0, lambda: self._log(
                    "No packages found on device", "warn"))
                return
            self.root.after(0, lambda: show_package_picker(
                self.root, pkgs, self.uninstall_var.set))
        threading.Thread(target=run, daemon=True).start()

    # ── Capture ───────────────────────────────────────────────────────────────

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
                subprocess.run(self._adb_prefix() + ["shell", "killall", "-2", "screenrecord"],
                               capture_output=True, timeout=5)
                try: proc.wait(timeout=3)
                except Exception: proc.kill()

            time.sleep(1)
            CAPTURES_DIR.mkdir(exist_ok=True)
            local = CAPTURES_DIR / f"rec_{datetime.now():%Y%m%d_%H%M%S}.mp4"
            ok = self._exec(self._adb_prefix() + ["pull", REMOTE_REC_PATH, str(local)],
                            success_msg=f"✓ Saved {local.relative_to(ROOT_DIR)}")
            if ok:
                subprocess.run(self._adb_prefix() + ["shell", "rm", REMOTE_REC_PATH],
                               capture_output=True, timeout=5)
        threading.Thread(target=run, daemon=True).start()

    # ── Logcat ────────────────────────────────────────────────────────────────

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
                make_button(self.custom_frame, name,
                            lambda s=script, n=name: self._run_script(s, n),
                            variant="custom").pack(fill=tk.X, pady=(0, 6))
        else:
            self.custom_sep.pack_forget()
            self.custom_frame.pack_forget()

    def _run_script(self, script: str, name: str):
        if not Path(script).exists():
            self._log(f"Script not found: {script}", "error")
            return
        self._log(f"Running: {name}", "info")
        self._run_async(["bash", script], success_msg=f"✓ {name} complete")

    # ── Settings ──────────────────────────────────────────────────────────────

    def _save_settings(self):
        save_settings(self.custom_actions, self.recent_apks, self.logcat_history)

    def _push_logcat_history(self, package: str, filter_text: str):
        """Add non-empty values to history (deduped, capped at 50)."""
        for key, value in (("package", package), ("filter", filter_text)):
            if not value:
                continue
            h = self.logcat_history.setdefault(key, [])
            if value in h:
                h.remove(value)
            h.insert(0, value)
            del h[50:]
        self._save_settings()

    def _open_settings(self):
        open_settings_dialog(self)

    # ── Subprocess helpers ────────────────────────────────────────────────────

    def _run_async(self, cmd: list[str], success_msg="Done"):
        threading.Thread(target=self._exec,
                         args=(cmd,), kwargs={"success_msg": success_msg},
                         daemon=True).start()

    def _exec(self, cmd: list[str], success_msg="Done") -> bool:
        self.root.after(0, lambda: self._log("$ " + " ".join(cmd), "dim"))
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True, errors="replace")
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
