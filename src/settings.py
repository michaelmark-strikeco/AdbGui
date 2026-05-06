"""JSON settings persistence."""

import json
from .theme import SETTINGS_FILE


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text())
        # Back-compat: very old versions wrote a bare list.
        if isinstance(data, list):
            return {"custom_actions": data, "recent_apks": []}
        return data
    except Exception:
        return {}


def save_settings(custom_actions: list[dict],
                  recent_apks: list[str],
                  logcat_history: dict | None = None):
    data = {
        "custom_actions": custom_actions,
        "recent_apks":    recent_apks,
    }
    if logcat_history is not None:
        data["logcat_history"] = logcat_history
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))
