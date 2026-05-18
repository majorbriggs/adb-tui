#!/usr/bin/env python3
"""Generate README screenshots using mocked ADB data."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from adb_tui.app import AdbTuiApp

OUT = Path("screenshots")
OUT.mkdir(exist_ok=True)

# Two devices for the device-list screenshot
DEVICES = ["emulator-5554", "192.168.1.100:5555"]
# Single device causes auto-navigation to ActionScreen — easier to work with
SINGLE_DEVICE = ["emulator-5554"]

PACKAGES = ["com.spotify.music", "com.spotify.lite", "com.spotify.podcast"]
SIZE = (100, 30)


def save(app: AdbTuiApp, name: str) -> None:
    (OUT / name).write_text(app.export_screenshot())
    screen = type(app.screen).__name__
    print(f"  {name}  (screen: {screen})")


async def shot_devices() -> None:
    """Device list screen with two devices."""
    with patch("adb_tui.adb.get_devices", return_value=DEVICES):
        app = AdbTuiApp()
        async with app.run_test(headless=True, size=SIZE) as pilot:
            await pilot.pause(1.0)
            save(app, "01_devices.svg")


async def shot_actions() -> None:
    """Action menu — single device triggers auto-navigation to ActionScreen."""
    with patch("adb_tui.adb.get_devices", return_value=SINGLE_DEVICE):
        app = AdbTuiApp()
        async with app.run_test(headless=True, size=SIZE) as pilot:
            await pilot.pause(1.0)
            save(app, "02_actions.svg")


async def shot_package_input() -> None:
    """Package input screen — select first action from ActionScreen."""
    with patch("adb_tui.adb.get_devices", return_value=SINGLE_DEVICE):
        app = AdbTuiApp()
        async with app.run_test(headless=True, size=SIZE) as pilot:
            await pilot.pause(1.0)   # auto-navigated to ActionScreen
            await pilot.press("enter")  # select Run App
            await pilot.pause(0.3)
            save(app, "03_package_input.svg")


async def shot_package_select() -> None:
    """Package selection list — search returns multiple matches."""
    with (
        patch("adb_tui.adb.get_devices", return_value=SINGLE_DEVICE),
        patch("adb_tui.adb.get_packages", return_value=PACKAGES),
    ):
        app = AdbTuiApp()
        async with app.run_test(headless=True, size=SIZE) as pilot:
            await pilot.pause(1.0)      # auto-navigated to ActionScreen
            await pilot.press("enter")  # select Run App -> PackageInputScreen
            await pilot.pause(0.3)
            for ch in "spotify":
                await pilot.press(ch)
            await pilot.press("enter")  # submit search
            await pilot.pause(1.0)      # wait for background thread
            save(app, "04_package_select.svg")


async def main() -> None:
    print("Generating screenshots...")
    await shot_devices()
    await shot_actions()
    await shot_package_input()
    await shot_package_select()
    print(f"Done — saved to {OUT}/")


if __name__ == "__main__":
    asyncio.run(main())
