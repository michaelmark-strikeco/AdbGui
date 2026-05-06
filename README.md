# AdbGui

A small Tkinter desktop app for installing APKs and launching `scrcpy` on an
Android device, with drag-and-drop, multi-device support, Wi-Fi ADB pairing,
and user-defined shell-script buttons.

![dark theme](https://img.shields.io/badge/theme-dark-0d1117) ![python](https://img.shields.io/badge/python-3.10%2B-3776ab) ![macOS](https://img.shields.io/badge/macOS-supported-success)

## Features

- **Drag & drop an APK** onto the window, or drop a **directory** to use the
  newest `.apk` inside it (recursive).
- **Multi-device aware** — every action runs against the device selected in the
  dropdown.
- **One-click actions:**
  - `Install APK` — `adb install -r <file>`
  - `Launch scrcpy`
  - `Install + Launch` — install, then auto-launch scrcpy on success
  - `📡 Wi-Fi ADB` — detects the device IP, runs `adb tcpip 5555`,
    then `adb connect <ip>:5555` so you can unplug USB
- **Custom actions** — add your own buttons that run any `.sh` script via the
  Settings dialog. Persisted to `~/.apk_installer_settings.json`.
- **Streaming log** — every adb / scrcpy / script invocation streams stdout
  into the panel with colour-coded tags.

## Requirements

| Tool             | Why                                | Install                                        |
| ---------------- | ---------------------------------- | ---------------------------------------------- |
| Python 3.10+     | runtime                            | already on macOS, or `brew install python`     |
| `adb`            | install / device control           | `brew install --cask android-platform-tools`   |
| `scrcpy`         | screen mirroring                   | `brew install scrcpy`                          |
| `tkinterdnd2`    | drag-and-drop (optional but nice)  | `pip install -r requirements.txt`              |

`adb` and `scrcpy` must be on your `PATH`.

## Install

```bash
cd AdbGui
pip install -r requirements.txt
```

## Run

```bash
python3 apk_installer.py
```

## Custom actions

Click **⚙ Settings** in the header. For each action, give it a name and point
it at a `.sh` file — it appears as a purple button in the sidebar and runs via
`bash <script>` when clicked.

Settings live at `~/.apk_installer_settings.json`:

```json
{
  "custom_actions": [
    { "name": "Run UI tests", "script": "/Users/me/scripts/ui-tests.sh" }
  ]
}
```

## Wi-Fi ADB notes

`adb tcpip 5555` kills the on-device USB daemon, so the USB entry disappears
from `adb devices` — that's expected. The button immediately follows up with
`adb connect <ip>:5555`, which adds the device back as `192.168.x.y:5555`.
After that, the cable is no longer needed.

If the IP can't be auto-detected, make sure Wi-Fi is on and the device is on
the same LAN as your machine.

## Project layout

```
AdbGui/
├── apk_installer.py       # the whole app
├── requirements.txt
└── README.md
```
