"""Pure adb command helpers — no UI, no state."""

import subprocess


def adb_prefix(device: str = "") -> list[str]:
    cmd = ["adb"]
    if device:
        cmd += ["-s", device]
    return cmd


def list_devices() -> list[str]:
    """Return serials of devices currently in `device` state."""
    r = subprocess.run(["adb", "devices"],
                       capture_output=True, text=True, timeout=5)
    return [
        line.split("\t")[0]
        for line in r.stdout.strip().splitlines()[1:]
        if "\tdevice" in line
    ]


def get_device_ip(device: str = "") -> str | None:
    """Best-effort device IP lookup via `adb shell ip -4 route`."""
    try:
        r = subprocess.run(
            adb_prefix(device) + ["shell", "ip", "-4", "route"],
            capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if " src " in line:
                return line.split(" src ", 1)[1].split()[0]
    except Exception:
        pass
    return None


def is_tcp_device(serial: str) -> bool:
    """A TCP serial looks like '192.168.x.y:5555'. USB serials never contain ':'."""
    if ":" not in serial:
        return False
    host = serial.rsplit(":", 1)[0]
    return host.count(".") == 3


def list_packages(device: str = "") -> list[str]:
    """Sorted list of all packages installed on the device."""
    r = subprocess.run(
        adb_prefix(device) + ["shell", "pm", "list", "packages"],
        capture_output=True, text=True, timeout=10)
    return sorted(
        line.removeprefix("package:").strip()
        for line in r.stdout.splitlines()
        if line.startswith("package:"))


def resolve_pid(device: str, package: str) -> str | None:
    """Return the PID of `package` on `device`, or None if not running."""
    try:
        r = subprocess.run(
            adb_prefix(device) + ["shell", "pidof", package],
            capture_output=True, text=True, timeout=5)
        pids = r.stdout.strip().split()
        return pids[0] if pids else None
    except Exception:
        return None
