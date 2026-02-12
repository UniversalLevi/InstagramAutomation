"""
Instagram app controller: high-level actions using driver + selectors with retries.
Mobile-only; no login automation. Assumes user is already logged in.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

from appium.webdriver import WebElement
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from . import selectors as sel

logger = logging.getLogger(__name__)


# Retry: short wait between attempts
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
    last_error = None
    while time.time() < end:
        for by_key, locator in selectors:
            try:
                by = by_map.get(by_key, by_key)
                el = driver.find_element(by, locator)
                if el and el.is_displayed():
                    return el
            except NoSuchElementException:
                continue
            except WebDriverException as e:
                last_error = e
                continue
        time.sleep(FIND_POLL)
    return None


def _tap_element(driver: WebDriver, element: WebElement) -> None:
    element.click()


def _scroll_up(driver: WebDriver, duration_ms: int = 300) -> None:
    size = driver.get_window_size()
    x = size["width"] // 2
    y1 = int(size["height"] * 0.7)
    y2 = int(size["height"] * 0.3)
    driver.swipe(x, y1, x, y2, duration_ms)


def _scroll_down(driver: WebDriver, duration_ms: int = 300) -> None:
    """
    Scroll UP in feed (changed from down to up as requested).
    Start from middle to avoid pull-to-refresh.
    """
    size = driver.get_window_size()
    x = size["width"] // 2
    # Scroll UP: from middle (50%) to top (20%)
    y1 = int(size["height"] * 0.5)  # Start from middle
    y2 = int(size["height"] * 0.2)   # Scroll UP
    driver.swipe(x, y1, x, y2, duration_ms)


def _scroll_reels_up(driver: WebDriver, duration_ms: int = 300) -> None:
    """
    Scroll UP in Reels (goes to next video).
    Reels scrolls vertically - swipe up to go to next video.
    """
    size = driver.get_window_size()
    x = size["width"] // 2
    # Swipe up from middle-bottom to middle-top for next Reel
    y1 = int(size["height"] * 0.7)  # Start from bottom area
    y2 = int(size["height"] * 0.3)   # Swipe up
    driver.swipe(x, y1, x, y2, duration_ms)


class InstagramApp:
    """High-level Instagram actions. All assume app is in foreground and user is logged in."""

    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver

    def scroll_feed_down(self, duration_sec: float = 1.0) -> bool:
        """Scroll feed UP (changed direction as requested). Returns True if scroll was performed."""
        try:
            _scroll_down(self.driver, int(duration_sec * 1000))  # Actually scrolls up now
            return True
        except WebDriverException:
            return False

    def scroll_feed_up(self, duration_sec: float = 1.0) -> bool:
        """Scroll feed up (pull to refresh or scroll up)."""
        try:
            _scroll_up(self.driver, int(duration_sec * 1000))
            return True
        except WebDriverException:
            return False

    def go_to_home_tab(self) -> bool:
        """Navigate to Home (feed) tab."""
        el = _find_element(self.driver, sel.home_tab_selectors(), timeout=2.0)
        if el:
            _tap_element(self.driver, el)
            time.sleep(0.5)  # Reduced wait
            return True
        return False

    def go_to_reels_tab(self) -> bool:
        """Navigate to Reels tab."""
        el = _find_element(self.driver, sel.reels_tab_selectors(), timeout=2.0)
        if el:
            _tap_element(self.driver, el)
            time.sleep(1.0)  # Wait for Reels to load
            return True
        return False

    def go_to_profile_tab(self) -> bool:
        """Navigate to Profile tab (own profile)."""
        el = _find_element(self.driver, sel.profile_tab_selectors(), timeout=2.0)
        if el:
            _tap_element(self.driver, el)
            time.sleep(0.5)  # Reduced wait
            return True
        return False

    def open_profile_from_feed(self) -> bool:
        """Tap first visible profile/username in feed to open that profile. Returns True if tapped."""
        el = _find_element(self.driver, sel.profile_username_in_feed_selectors(), timeout=3.0)
        if el:
            _tap_element(self.driver, el)
            time.sleep(1.5)  # Wait for profile to load
            return True
        return False

    def tap_back(self) -> bool:
        """Tap back to return to previous screen."""
        el = _find_element(self.driver, sel.back_button_selectors(), timeout=2.0)
        if el:
            _tap_element(self.driver, el)
            time.sleep(0.5)  # Reduced wait
            return True
        # Fallback: use Android back button
        try:
            self.driver.back()
            time.sleep(0.5)
            return True
        except Exception:
            return False

    def like_current_post(self) -> bool:
        """
        Like the currently visible post (e.g. in feed or profile).
        Returns True if like was tapped; does not guarantee like succeeded.
        """
        # Avoid double-like: if already liked, skip
        if _find_element(self.driver, sel.like_button_liked_selectors(), timeout=0.5):
            return False
        
        # Try to find and tap like button with longer timeout
        el = _find_element(self.driver, sel.like_button_selectors(), timeout=3.0)
        if el:
            try:
                _tap_element(self.driver, el)
                time.sleep(0.8)  # Wait a bit longer to see if like registered
                return True
            except Exception as e:
                logger.warning("Failed to tap like button: %s", e)
                return False
        
        # Fallback: try double-tap on post image (common Instagram gesture)
        try:
            size = self.driver.get_window_size()
            x = size["width"] // 2
            y = int(size["height"] * 0.4)  # Tap on post image area
            self.driver.tap([(x, y)], 100)  # Double tap simulation
            time.sleep(0.5)
            self.driver.tap([(x, y)], 100)
            time.sleep(0.8)
            return True
        except Exception as e:
            logger.warning("Double-tap fallback failed: %s", e)
            return False

    def scroll_feed_for_seconds(self, total_sec: float, step_sec: float = 0.8) -> int:
        """
        Scroll feed UP repeatedly for about total_sec. step_sec between scrolls.
        Returns approximate number of scrolls performed.
        Faster scrolling with shorter delays. Avoids pull-to-refresh by scrolling from middle.
        """
        count = 0
        end = time.time() + total_sec
        while time.time() < end and count < MAX_SWIPES:
            if self.scroll_feed_down(0.3):  # Faster swipe duration (scrolls up now)
                count += 1
            # Small wait to let content load, but shorter for speed
            time.sleep(step_sec)
        return count

    def scroll_reels_for_videos(self, num_videos: int = 5, step_sec: float = 2.0) -> int:
        """
        Scroll through Reels (swipe up to next video) for num_videos.
        Returns number of videos scrolled through.
        """
        count = 0
        for _ in range(num_videos):
            try:
                _scroll_reels_up(self.driver, 300)
                count += 1
                time.sleep(step_sec)  # Watch video for a bit
            except WebDriverException:
                break
        return count

    def like_reel(self) -> bool:
        """
        Like the current Reel video. Tries double-tap first, then like button.
        Returns True if like was performed.
        """
        # Avoid double-like: if already liked, skip
        if _find_element(self.driver, sel.like_button_liked_selectors(), timeout=0.5):
            return False
        
        # Try double-tap on video (common Reels gesture)
        try:
            size = self.driver.get_window_size()
            x = size["width"] // 2
            y = int(size["height"] * 0.5)  # Tap center of screen (video area)
            self.driver.tap([(x, y)], 100)  # First tap
            time.sleep(0.2)
            self.driver.tap([(x, y)], 100)  # Second tap (double-tap)
            time.sleep(0.8)
            # Check if it worked
            if _find_element(self.driver, sel.like_button_liked_selectors(), timeout=0.5):
                logger.info("Reel liked via double-tap")
                return True
        except Exception as e:
            logger.warning("Double-tap failed: %s", e)
        
        # Fallback: try like button
        el = _find_element(self.driver, sel.like_button_selectors(), timeout=2.0)
        if el:
            try:
                _tap_element(self.driver, el)
                time.sleep(0.8)
                logger.info("Reel liked via like button")
                return True
            except Exception as e:
                logger.warning("Like button tap failed: %s", e)
        
        return False

    def has_block_warning(self) -> bool:
        """Return True if a block/warning message is visible (health check)."""
        return _find_element(self.driver, sel.block_warning_selectors(), timeout=1.0) is not None
