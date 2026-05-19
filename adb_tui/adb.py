from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from enum import Enum


class AdbError(Exception):
    def __init__(self, returncode: int, stderr: str) -> None:
        self.returncode = returncode
        self.stderr = stderr.strip()
        super().__init__(self.stderr or f"adb exited with code {returncode}")


class Action(Enum):
    RUN = "Run App"
    KILL = "Kill App"
    UNINSTALL = "Uninstall App"
    CLEAR_CACHE = "Clear Cache"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["adb", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise AdbError(result.returncode, result.stderr)
    return result


_IP_PATTERN = re.compile(r"^\d+\.\d+\.\d+\.\d+(:\d+)?$")

# ---------------------------------------------------------------------------
# Device queries
# ---------------------------------------------------------------------------


def get_devices() -> list[str]:
    result = _run("devices")
    devices: list[str] = []
    for line in result.stdout.splitlines()[1:]:  # skip "List of devices" header
        stripped = line.strip()
        if stripped and "offline" not in stripped:
            devices.append(stripped.split()[0])
    return devices


def format_device(device: str) -> str:
    """Return a display-friendly device label."""
    if _IP_PATTERN.match(device):
        return device.split(":")[0]  # show IP without port for WiFi devices
    return device


# ---------------------------------------------------------------------------
# Package queries
# ---------------------------------------------------------------------------


def get_packages(device: str, partial: str) -> list[str]:
    result = _run("-s", device, "shell", "pm", "list", "packages")
    packages: list[str] = []
    for line in result.stdout.splitlines():
        pkg = line.strip().rstrip("\r").removeprefix("package:")
        if pkg and partial.lower() in pkg.lower():
            packages.append(pkg)
    return sorted(packages)


# ---------------------------------------------------------------------------
# Device actions
# ---------------------------------------------------------------------------


def launch_app(device: str, package: str) -> None:
    _run(
        "-s",
        device,
        "shell",
        "monkey",
        "-p",
        package,
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
    )


def kill_app(device: str, package: str) -> None:
    _run("-s", device, "shell", "am", "force-stop", package)


def uninstall_app(device: str, package: str) -> None:
    _run("-s", device, "uninstall", package)


def clear_cache(device: str, package: str) -> None:
    _run("-s", device, "shell", "pm", "clear", package)


_ACTION_HANDLERS: dict[Action, tuple[Callable[[str, str], None], str]] = {
    Action.RUN: (launch_app, "Launched"),
    Action.KILL: (kill_app, "Killed"),
    Action.UNINSTALL: (uninstall_app, "Uninstalled"),
    Action.CLEAR_CACHE: (clear_cache, "Cleared cache for"),
}


def run_action(action: Action, device: str, package: str) -> str:
    """Execute an action and return a human-readable success message."""
    handler, prefix = _ACTION_HANDLERS[action]
    handler(device, package)
    return f"{prefix} {package}"
