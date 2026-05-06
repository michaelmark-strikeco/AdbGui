"""Color palette, button-style table, and path constants.

Pure data — no UI imports — so anything can pull from it without cycles.
"""

from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
# This module lives in AdbGui/src/, so go up one level for the project root
# so settings.json and captures/ stay next to apk_installer.py.
ROOT_DIR        = Path(__file__).resolve().parent.parent
SETTINGS_FILE   = ROOT_DIR / ".apk_installer_settings.json"
CAPTURES_DIR    = ROOT_DIR / "captures"
REMOTE_REC_PATH = "/sdcard/_adbgui_rec.mp4"
RECENT_LIMIT    = 10

# ── Colour palette ────────────────────────────────────────────────────────────
# Each key is a semantic role, not a palette name.
# Every bg/fg pair has contrast ratio ≥ 4.5:1.
T = {
    # Backgrounds
    "bg":          "#0d1117",
    "surface":     "#161b22",
    "raised":      "#21262d",
    "input":       "#0d1117",
    "border":      "#30363d",

    # Text
    "text":        "#e6edf3",
    "subtext":     "#8b949e",
    "title":       "#79c0ff",

    # Buttons — all use white text against a dark enough bg
    "btn2_bg":     "#3d444d",   "btn2_fg":     "#ffffff", "btn2_hover":  "#4d5460",

    "btn_install_bg":  "#1f6feb", "btn_install_fg":  "#ffffff",
    "btn_scrcpy_bg":   "#1a7f37", "btn_scrcpy_fg":   "#ffffff",
    "btn_combo_bg":    "#9a6700", "btn_combo_fg":    "#ffffff",

    "btn_custom_bg":   "#6e40c9", "btn_custom_fg":   "#ffffff", "btn_custom_hover": "#7d4fd6",
    "btn_net_bg":      "#1b6e7c", "btn_net_fg":      "#ffffff", "btn_net_hover":    "#22808f",
    "btn_close_bg":    "#8b3a3a", "btn_close_fg":    "#ffffff", "btn_close_hover":  "#a04a4a",

    # Log tags
    "log_success": "#3fb950",
    "log_error":   "#f85149",
    "log_info":    "#79c0ff",
    "log_warn":    "#d29922",
    "log_dim":     "#8b949e",
}

# variant → (bg_key, fg_key, hover_key, font_size, pady)
BTN_STYLES = {
    "secondary": ("btn2_bg",        "btn2_fg",        "btn2_hover",        11, 5),
    "install":   ("btn_install_bg", "btn_install_fg", "btn_install_bg",    12, 8),
    "scrcpy":    ("btn_scrcpy_bg",  "btn_scrcpy_fg",  "btn_scrcpy_bg",     12, 8),
    "combo":     ("btn_combo_bg",   "btn_combo_fg",   "btn_combo_bg",      12, 8),
    "custom":    ("btn_custom_bg",  "btn_custom_fg",  "btn_custom_hover",  12, 8),
    "network":   ("btn_net_bg",     "btn_net_fg",     "btn_net_hover",     12, 8),
    "close":     ("btn_close_bg",   "btn_close_fg",   "btn_close_hover",   12, 8),
}
