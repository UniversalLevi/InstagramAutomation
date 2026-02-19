"""
Appium driver for Android. Connects to device/emulator and launches TikTok.
No automated login: user must be already logged in on the device.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from appium import webdriver
from appium.options.android import UiAutomator2Options

# Project root: tiktok/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def create_driver(
    package: str = "com.zhiliaoapp.musically",
    activity: Optional[str] = None,
    adb_serial: Optional[str] = None,
    appium_url: str = "http://127.0.0.1:4723",
    caps_override: Optional[Dict[str, Any]] = None,
) -> webdriver.WebDriver:
    """
    Create Appium WebDriver for TikTok on Android.
    Assumes Appium server is running and device is connected.
    If activity is None, we activate the app after creating the driver (recommended for noReset=True).
    """
    options = UiAutomator2Options()
    options.app_package = package
    options.no_reset = True
    options.full_reset = False

    if activity:
        options.app_activity = activity

    if adb_serial:
        options.udid = adb_serial

    if caps_override:
        for k, v in caps_override.items():
            setattr(options, k, v)

    driver = webdriver.Remote(appium_url, options=options)

    if not activity:
        try:
            driver.activate_app(package)
            time.sleep(1)
        except Exception:
            import subprocess
            adb_cmd = ["adb"]
            if adb_serial:
                adb_cmd.extend(["-s", adb_serial])
            adb_cmd.extend(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
            try:
                subprocess.run(adb_cmd, capture_output=True, timeout=5, check=False)
                time.sleep(2)
            except Exception:
                pass

    return driver


def ensure_app_foreground(driver: webdriver.WebDriver, package: str = "com.zhiliaoapp.musically") -> None:
    """Bring TikTok to foreground if not already."""
    try:
        driver.activate_app(package)
    except Exception:
        driver.start_activity(package, None)
    time.sleep(1)
