# AdbGui

A Tkinter desktop app that wraps the everyday Android dev workflow:
install APKs, launch `scrcpy`, tail logcat, capture screenshots/recordings,
uninstall apps, pair over Wi-Fi, and add your own shell-script buttons.

![dark theme](https://img.shields.io/badge/theme-dark-0d1117) ![python](https://img.shields.io/badge/python-3.10%2B-3776ab) ![macOS](https://img.shields.io/badge/macOS-supported-success)

## Features

- **Drag & drop an APK** onto the window, or drop a **directory** to use the
  newest `.apk` inside it (recursive).
- **Multi-device aware** — every action runs against the device selected in the
  dropdown.
- **Recent APKs** — the 10 most recently installed APKs are remembered and
  shown in a dropdown for one-click re-selection.
- **One-click actions:**
  - `Install APK` — `adb install -r <file>`
  - `Launch scrcpy`
  - `Install + Launch` — install, then auto-launch scrcpy on success
  - `📡 Wi-Fi ADB` — detects the device IP, runs `adb tcpip 5555`,
    then `adb connect <ip>:5555` so you can unplug USB
  - `🔌 Close Wi-Fi ADB` (only shown when a TCP device is selected) —
    reverts the on-device daemon to USB and disconnects locally
- **Uninstall** — type or pick a package from a searchable list of every
  package installed on the device.
- **Capture:**
  - `📸 Screenshot` — saves a PNG to `captures/`
  - `🔴 Record Screen` — toggle on/off; pulls the MP4 to `captures/`
- **Logcat viewer** — separate window with package, level, and substring
  filters; colour-coded by level; auto-scroll toggle; capped at 5,000 lines
  to keep memory bounded.
- **Custom actions** — add your own buttons that run any `.sh` script via the
  Settings dialog. Persisted alongside other settings.
- **Streaming log** — every adb / scrcpy / script invocation streams stdout
  into the bottom panel with colour-coded tags.

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

Settings live in `.apk_installer_settings.json` next to the script (hidden):

```json
{
  "custom_actions": [
    { "name": "Run UI tests", "script": "/Users/me/scripts/ui-tests.sh" }
  ],
  "recent_apks": [
    "/Users/me/Downloads/myapp-debug.apk"
  ]
}
```

## Logcat viewer

Click **🪵 Logcat** in the header.

- **Package** — if the package is currently running, the viewer resolves it to
  a PID via `adb shell pidof` and uses `logcat --pid=<pid>` (the cleanest filter).
  If it isn't running, you get all output and a warning in the status line.
- **Level** — V/D/I/W/E (Verbose → Error). Sets `*:<level>` on the logcat
  command so the device-side filter does the heavy lifting.
- **Filter** — additional substring filter applied client-side.
- **Auto-scroll** — toggle whether new lines stick to the bottom.
- **Clear** — wipes the buffer.
- The buffer is capped at the last 5,000 lines per session.

The viewer is bound to whichever device is selected in the main window when
**▶ Start** is pressed. To switch devices, stop, change the selection, and start
again.

## Capture

- **Screenshot** uses `adb exec-out screencap -p` and writes the PNG straight
  to disk — no on-device temp file.
- **Screen Record** runs `adb shell screenrecord /sdcard/_adbgui_rec.mp4`. When
  you click **Stop Recording**, the local `adb shell` is sent `SIGINT`, which
  ends `screenrecord` cleanly. The file is then `adb pull`ed to `captures/`
  and removed from the device.
- Android caps `screenrecord` at 3 minutes per invocation.

## Wi-Fi ADB notes

`adb tcpip 5555` kills the on-device USB daemon, so the USB entry disappears
from `adb devices` — that's expected. The button immediately follows up with
`adb connect <ip>:5555`, which adds the device back as `192.168.x.y:5555`.
After that, the cable is no longer needed.

If the IP can't be auto-detected, make sure Wi-Fi is on and the device is on
the same LAN as your machine.

To revert: select the TCP device in the dropdown and click
**🔌 Close Wi-Fi ADB**.

## Project layout

```
AdbGui/
├── apk_installer.py                 # the whole app
├── requirements.txt
├── README.md
├── .apk_installer_settings.json     # settings (hidden, auto-created)
└── captures/                        # screenshots and recordings (auto-created)
```
