"""
TikTok app controller: high-level actions using driver + selectors with retries.
Mobile-only; no login automation. Assumes user is already logged in.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

from appium.webdriver import WebElement
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)
from selenium.webdriver.remote.webdriver import WebDriver

from . import selectors as sel

logger = logging.getLogger(__name__)

FIND_TIMEOUT = 2
FIND_POLL = 0.5
MAX_SWIPES = 50


def _find_element(driver: WebDriver, selectors: List[Tuple[str, str]], timeout: float = FIND_TIMEOUT) -> Optional[WebElement]:
    by_map = {
        "accessibility id": AppiumBy.ACCESSIBILITY_ID,
        "id": AppiumBy.ID,
        "xpath": AppiumBy.XPATH,
        "class name": AppiumBy.CLASS_NAME,
    }
    end = time.time() + timeout
    while time.time() < end:
        for by_key, locator in selectors:
            try:
                by = by_map.get(by_key, by_key)
                el = driver.find_element(by, locator)
                if el and el.is_displayed():
                    return el
            except NoSuchElementException:
                continue
            except WebDriverException:
                continue
        time.sleep(FIND_POLL)
    return None


def _tap_element(driver: WebDriver, element: WebElement) -> None:
    element.click()


def _tap_element_robust(driver: WebDriver, element: WebElement) -> bool:
    """Tap element; fallback to tap at center on stale/intercepted."""
    try:
        element.click()
        return True
    except (StaleElementReferenceException, ElementClickInterceptedException):
        pass
    except Exception:
        pass
    try:
        loc = element.location
        sz = element.size
        if loc and sz:
            x = loc.get("x", 0) + sz.get("width", 0) // 2
            y = loc.get("y", 0) + sz.get("height", 0) // 2
            driver.tap([(x, y)], 100)
            return True
    except Exception:
        pass
    return False


def _scroll_fyp_up(driver: WebDriver, duration_ms: int = 300) -> None:
    """Swipe up = next video on FYP."""
    size = driver.get_window_size()
    x = size["width"] // 2
    y1 = int(size["height"] * 0.7)
    y2 = int(size["height"] * 0.3)
    driver.swipe(x, y1, x, y2, duration_ms)


class TikTokApp:
    """High-level TikTok actions. App must be in foreground and user logged in."""

    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver

    def go_to_home_tab(self) -> bool:
        """Navigate to Home (For You feed)."""
        el = _find_element(self.driver, sel.home_tab_selectors(), timeout=2.0)
        if el:
            _tap_element(self.driver, el)
            time.sleep(1.0)
            return True
        return False

    def go_to_profile_tab(self) -> bool:
        """Navigate to Profile / Me tab (own profile)."""
        el = _find_element(self.driver, sel.profile_tab_selectors(), timeout=2.0)
        if el:
            _tap_element(self.driver, el)
            time.sleep(0.5)
            return True
        return False

    def scroll_fyp(self, duration_sec: float = 0.3) -> bool:
        """Scroll to next video (swipe up). Returns True if swipe was performed."""
        try:
            _scroll_fyp_up(self.driver, int(duration_sec * 1000))
            return True
        except WebDriverException:
            return False

    def scroll_fyp_for_videos(self, num_videos: int = 5, step_sec: float = 2.0) -> int:
        """Scroll through FYP for num_videos. Returns count of scrolls."""
        count = 0
        for _ in range(num_videos):
            try:
                _scroll_fyp_up(self.driver, 300)
                count += 1
                time.sleep(step_sec)
            except WebDriverException:
                break
        return count

    def like_current_video(self) -> bool:
        """Like the current FYP video. Returns True if like was performed."""
        if _find_element(self.driver, sel.like_button_liked_selectors(), timeout=0.5):
            return False
        el = _find_element(self.driver, sel.like_button_selectors(), timeout=3.0)
        if el:
            try:
                _tap_element(self.driver, el)
                time.sleep(0.8)
                return True
            except Exception as e:
                logger.warning("Failed to tap like: %s", e)
                return False
        # Fallback: double-tap on video area
        try:
            size = self.driver.get_window_size()
            x = size["width"] // 2
            y = int(size["height"] * 0.5)
            self.driver.tap([(x, y)], 100)
            time.sleep(0.2)
            self.driver.tap([(x, y)], 100)
            time.sleep(0.8)
            return True
        except Exception as e:
            logger.warning("Double-tap fallback failed: %s", e)
            return False

    def visit_profile_from_feed(self) -> bool:
        """Tap username/avatar on current video to open creator profile."""
        el = _find_element(self.driver, sel.profile_username_in_feed_selectors(), timeout=3.0)
        if el:
            _tap_element(self.driver, el)
            time.sleep(1.5)
            return True
        return False

    def tap_back(self) -> bool:
        """Go back to previous screen."""
        el = _find_element(self.driver, sel.back_button_selectors(), timeout=2.0)
        if el:
            _tap_element(self.driver, el)
            time.sleep(0.5)
            return True
        try:
            self.driver.back()
            time.sleep(0.5)
            return True
        except Exception:
            return False

    def has_block_warning(self) -> bool:
        """True if block/rate-limit warning is visible."""
        return _find_element(self.driver, sel.block_warning_selectors(), timeout=1.0) is not None
