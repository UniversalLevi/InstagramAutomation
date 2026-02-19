"""
Appium driver for Android. Connects to device/emulator and launches Instagram.
No automated login: user must be already logged in on the device.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional

from appium import webdriver
from appium.options.android import UiAutomator2Options

# Project root for config
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def create_driver(
    package: str = "com.instagram.android",
    activity: Optional[str] = None,
    adb_serial: Optional[str] = None,
    appium_url: str = "http://127.0.0.1:4723",
    caps_override: Optional[Dict[str, Any]] = None,
) -> webdriver.WebDriver:
    """
    Create Appium WebDriver for Instagram on Android.
    Assumes Appium server is running (e.g. appium or appium server) and device is connected.
    If activity is None, we'll activate the app after creating the driver (recommended for noReset=True).
    """
    options = UiAutomator2Options()
    options.app_package = package
    # Don't clear app data: we reuse existing session (manual login only)
    options.no_reset = True
    options.full_reset = False
    
    # Only set activity if provided (otherwise use activate_app after driver creation)
    if activity:
        options.app_activity = activity

    if adb_serial:
        options.udid = adb_serial

    if caps_override:
        for k, v in caps_override.items():
            setattr(options, k, v)

    driver = webdriver.Remote(appium_url, options=options)
    
    # If no activity was specified, activate the app (brings it to foreground)
    # This is more reliable than specifying an activity name that might not exist
    if not activity:
        try:
            driver.activate_app(package)
            time.sleep(1)
        except Exception:
            # Fallback: use adb to launch the app's main launcher activity
            import subprocess
            adb_cmd = ["adb"]
            if adb_serial:
                adb_cmd.extend(["-s", adb_serial])
            # Use monkey to launch app (doesn't require exact activity name)
            adb_cmd.extend(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
            try:
                subprocess.run(adb_cmd, capture_output=True, timeout=5, check=False)
                time.sleep(2)
            except Exception:
                pass  # If this fails, user can manually open Instagram
    
    return driver


def ensure_app_foreground(driver: webdriver.WebDriver, package: str = "com.instagram.android") -> None:
    """Bring Instagram to foreground if not already."""
    try:
        driver.activate_app(package)
    except Exception:
        driver.start_activity(package, None)
    time.sleep(1)
