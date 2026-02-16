"""
Appium-based Instagram posting module.
Uses see-decide-act state machine: detect screen state, decide action, act, repeat until SUCCESS or fail.
"""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from src.device import post_selectors as post_sel
from src.posting.models import MediaType, PostItem
from src.posting.screen_state import (
    PostingScreenState,
    get_posting_screen_state,
    get_action_for_state,
    find_element_by_intent,
    dump_screen_summary,
)

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.device.instagram_app import _find_element, _tap_element, _tap_element_robust

logger = logging.getLogger(__name__)

MAX_POST_STEPS = 25
UNKNOWN_STEPS_BEFORE_FAIL = 4
STEP_SLEEP_SEC = 1.5


class InstagramPoster:
    """Handles posting to Instagram via Appium."""
    
    def __init__(self, driver, account_id: str, adb_serial: Optional[str] = None):
        self.driver = driver
        self.account_id = account_id
        self.adb_serial = adb_serial  # e.g. emulator-5554 for adb -s
    
    def _adb_cmd(self, args: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """Run adb with optional -s serial."""
        cmd = ["adb"]
        if self.adb_serial:
            cmd.extend(["-s", self.adb_serial])
        cmd.extend(args)
        return subprocess.run(cmd, capture_output=True, timeout=timeout)
    
    def post_item(self, post_item: PostItem) -> bool:
        """Post a PostItem. Returns True if successful."""
        try:
            if post_item.media_type == MediaType.PHOTO:
                return self.post_photo(post_item.file_paths[0], post_item.caption, post_item.hashtags)
            elif post_item.media_type == MediaType.VIDEO:
                return self.post_video(post_item.file_paths[0], post_item.caption, post_item.hashtags)
            elif post_item.media_type == MediaType.REEL:
                return self.post_reel(post_item.file_paths[0], post_item.caption, post_item.hashtags)
            elif post_item.media_type == MediaType.CAROUSEL:
                return self.post_carousel(post_item.file_paths, post_item.caption, post_item.hashtags)
            else:
                logger.error("Unknown media type: %s", post_item.media_type)
                return False
        except Exception as e:
            logger.error("Failed to post item: %s", e, exc_info=True)
            return False
    
    def _find_create_post_button_on_profile(self):
        """Find the + (create post) button on Profile screen - top left in action bar."""
        from appium.webdriver.common.appiumby import AppiumBy
        
        # 1) Profile-specific selectors (action bar, toolbar, content-desc)
        el = _find_element(self.driver, post_sel.create_post_button_on_profile_selectors(), timeout=3.0)
        if el:
            return el
        
        # 2) UIAutomator2: description contains New/Create/post
        for desc in ["New post", "New Post", "Create", "new post", "create", "Add"]:
            try:
                el = self.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().descriptionContains("{desc}")')
                if el and el.is_displayed():
                    return el
            except Exception:
                continue
        
        try:
            el = self.driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().descriptionContains("New").descriptionContains("post")')
            if el and el.is_displayed():
                return el
        except Exception:
            pass
        
        # 3) Top-left area: any clickable ImageButton/ImageView in top 15% of screen (action bar)
        try:
            size = self.driver.get_window_size()
            h, w = size["height"], size["width"]
            top_y_max = int(h * 0.15)
            
            for xpath in ["//android.widget.ImageButton", "//android.widget.ImageView"]:
                els = self.driver.find_elements(AppiumBy.XPATH, xpath)
                for el in els:
                    try:
                        if not el.is_displayed() or not el.get_attribute("clickable") == "true":
                            continue
                        loc = el.location
                        if loc["y"] > top_y_max:
                            continue
                        # Prefer left half of screen (top-left + button)
                        if loc["x"] > w // 2:
                            continue
                        return el
                    except Exception:
                        continue
        except Exception:
            pass
        
        return None

    def _dismiss_overlays(self, back_presses: int = 3) -> None:
        """Press Back to close any open dialog, story viewer, or extra screen before starting post flow."""
        try:
            for i in range(back_presses):
                try:
                    self.driver.back()
                    time.sleep(0.8)
                except Exception as e:
                    logger.debug("Back press %d failed: %s", i + 1, e)
                    break
            time.sleep(0.5)
        except Exception as e:
            logger.debug("Dismiss overlays failed (non-fatal): %s", e)
    
    def _navigate_to_create_post(self) -> bool:
        """Navigate to Profile first, then tap the + button (top left) to open create post."""
        try:
            from src.device.instagram_app import InstagramApp
            
            app = InstagramApp(self.driver)
            
            # 0) Close any open overlay/dialog so we start from a clean state
            self._dismiss_overlays(back_presses=3)
            time.sleep(1)
            
            # 1) Go to Profile tab first
            logger.info("Navigating to Profile tab...")
            if not app.go_to_profile_tab():
                logger.error("Failed to open Profile tab")
                return False
            time.sleep(2)
            
            # 2) Find and tap the + button on profile (top left)
            el = self._find_create_post_button_on_profile()
            if el:
                logger.info("Found create post (+) button on profile, tapping...")
                _tap_element(self.driver, el)
                time.sleep(2)
                # Confirm we're in create post flow (gallery or photo/video/reel options)
                if _find_element(self.driver, post_sel.gallery_selectors(), timeout=3.0) or _find_element(self.driver, post_sel.photo_selectors(), timeout=2.0):
                    return True
                return True
            
            # 3) Fallback: tap top-left coordinates (where + usually is on profile)
            try:
                size = self.driver.get_window_size()
                x = int(size["width"] * 0.12)
                y = int(size["height"] * 0.08)
                logger.warning("Tapping top-left fallback at (%s, %s) for + button", x, y)
                self.driver.tap([(x, y)], duration=100)
                time.sleep(2)
                if _find_element(self.driver, post_sel.gallery_selectors(), timeout=3.0) or _find_element(self.driver, post_sel.photo_selectors(), timeout=2.0):
                    return True
            except Exception as fallback_err:
                logger.debug("Top-left tap fallback failed: %s", fallback_err)
            
            logger.error("Could not find create post button on Profile")
            return False
        except Exception as e:
            logger.error("Failed to navigate to create post: %s", e, exc_info=True)
            return False
    
    def _push_file_to_device(self, file_path: Path) -> Optional[str]:
        """Push file to device via ADB. Uses DCIM so gallery/Instagram can see it. Verifies file exists. Returns device path if successful."""
        # Use DCIM so Android media scanner and Instagram picker can find the file
        device_dir = "/sdcard/DCIM/InstagramPost/"
        device_filename = file_path.name
        device_file_path = device_dir + device_filename
        
        try:
            # Ensure directory exists on device
            self._adb_cmd(["shell", "mkdir", "-p", device_dir], timeout=10)
            
            # Push file via ADB
            result = self._adb_cmd(["push", str(file_path), device_file_path], timeout=60)
            
            if result.returncode != 0:
                logger.error("adb push failed: %s", (result.stderr or result.stdout or b"").decode(errors="replace"))
                return None
            
            logger.info("Pushed file to device: %s", device_file_path)
            
            # Verify file actually exists on device
            check = self._adb_cmd(["shell", f"test -f '{device_file_path}' && echo exists"], timeout=10)
            out = (check.stdout or b"").decode().strip()
            if "exists" not in out:
                logger.error("File verification failed: file not found on device at %s", device_file_path)
                return None
            
            # Trigger media scanner so gallery/Instagram see the new file
            try:
                self._adb_cmd(["shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{device_file_path}"], timeout=5)
                time.sleep(1)
            except Exception as scan_err:
                logger.warning("Media scanner trigger failed (non-fatal): %s", scan_err)
            
            return device_file_path
        except subprocess.TimeoutExpired:
            logger.error("adb push or verify timed out")
            return None
        except Exception as e:
            logger.error("Error pushing file to device: %s", e)
            return None
    
    def _select_media_type(self, media_type: MediaType) -> bool:
        """Select media type (Photo/Video/Reel) from create post menu."""
        try:
            time.sleep(1)
            
            if media_type == MediaType.PHOTO:
                selectors = post_sel.photo_selectors()
            elif media_type == MediaType.VIDEO:
                selectors = post_sel.video_selectors()
            elif media_type == MediaType.REEL:
                selectors = post_sel.reel_selectors()
            else:
                return False
            
            el = _find_element(self.driver, selectors, timeout=3.0)
            if el:
                _tap_element(self.driver, el)
                time.sleep(2)
                return True
            return False
        except Exception as e:
            logger.error("Failed to select media type: %s", e)
            return False
    
    def _select_file_from_gallery(self, file_path: Path) -> bool:
        """Select our file from gallery. We pushed to DCIM so it should appear in Recent/first positions."""
        try:
            # Open Gallery option if present (some flows open gallery directly)
            gallery_el = _find_element(self.driver, post_sel.gallery_selectors(), timeout=4.0)
            if gallery_el:
                _tap_element(self.driver, gallery_el)
                time.sleep(2.5)  # Let gallery load and show our recently pushed file
            else:
                time.sleep(1.5)
            
            # Try to tap our file: we pushed to DCIM so it's often first/most recent in grid
            # Try multiple selectors for first image in gallery
            from appium.webdriver.common.appiumby import AppiumBy
            for xpath in [
                "//android.widget.ImageView[@clickable='true'][1]",
                "//android.widget.ImageView[1]",
                "//*[contains(@resource-id, 'thumbnail') or contains(@resource-id, 'image')][1]",
                "//androidx.recyclerview.widget.RecyclerView//android.widget.ImageView[1]",
                "//*[@clickable='true']//android.widget.ImageView[1]",
            ]:
                try:
                    image_el = self.driver.find_element(AppiumBy.XPATH, xpath)
                    if image_el and image_el.is_displayed():
                        image_el.click()
                        time.sleep(1.5)
                        # If we see Next or Done, we likely selected something
                        if _find_element(self.driver, post_sel.next_button_selectors(), timeout=1.0) or _find_element(self.driver, post_sel.done_button_selectors(), timeout=1.0):
                            return True
                        return True
                except Exception:
                    continue
            
            # Fallback: tap Done if picker already had a selection
            el = _find_element(self.driver, post_sel.done_button_selectors(), timeout=2.0)
            if el:
                _tap_element(self.driver, el)
                time.sleep(2)
                return True
            
            return False
        except Exception as e:
            logger.error("Failed to select file from gallery: %s", e)
            return False

    def _carousel_back_to_picker(self, presses: int = 2) -> None:
        """Press Back to recover from mistouch (e.g. left gallery or wrong screen)."""
        for _ in range(presses):
            try:
                self.driver.back()
                time.sleep(1.0)
            except Exception:
                break

    def _select_all_carousel_photos(self, file_paths: List[Path], max_retries_per_image: int = 2) -> bool:
        """
        Phase 1 for carousel: select all photos in the picker first.
        Uses retries and Back-on-fail to recover from mistouches. Returns True when all selected.
        """
        if not file_paths:
            return False
        # --- First image ---
        for attempt in range(max_retries_per_image):
            if self._select_file_from_gallery(file_paths[0]):
                logger.info("Carousel: selected first image")
                break
            if attempt < max_retries_per_image - 1:
                logger.warning("Carousel: first image select failed, backing and retrying")
                self._carousel_back_to_picker(1)
                time.sleep(1.5)
        else:
            logger.error("Carousel: failed to select first image")
            return False

        # --- Remaining images: Add more -> select from gallery ---
        for i, fp in enumerate(file_paths[1:], start=2):
            added = False
            for attempt in range(max_retries_per_image):
                add_el = _find_element(self.driver, post_sel.add_more_selectors(), timeout=3.0)
                if add_el:
                    try:
                        _tap_element_robust(self.driver, add_el)
                        time.sleep(2.0)
                    except Exception as e:
                        logger.debug("Add more tap failed: %s", e)
                        if attempt < max_retries_per_image - 1:
                            self._carousel_back_to_picker(1)
                            time.sleep(1.5)
                        continue
                else:
                    if attempt < max_retries_per_image - 1:
                        self._carousel_back_to_picker(1)
                        time.sleep(1.5)
                    continue

                if self._select_file_from_gallery(fp):
                    logger.info("Carousel: selected image %d/%d", i, len(file_paths))
                    added = True
                    break
                if attempt < max_retries_per_image - 1:
                    logger.warning("Carousel: select image %d failed, backing and retrying", i)
                    self._carousel_back_to_picker(1)
                    time.sleep(1.5)
            if not added:
                logger.error("Carousel: failed to add image %d", i)
                return False
            time.sleep(0.8)

        # Confirm we're in composer: Next or Done visible (all photos picked)
        time.sleep(1.0)
        next_el = _find_element(self.driver, post_sel.next_button_selectors(), timeout=2.0)
        done_el = _find_element(self.driver, post_sel.done_button_selectors(), timeout=2.0)
        if next_el or done_el:
            return True
        # Fallback: tap by position where Next/Done often is (bottom-right) to proceed
        try:
            size = self.driver.get_window_size()
            w, h = size["width"], size["height"]
            for rx, ry in [(0.9, 0.92), (0.5, 0.92)]:
                self.driver.tap([(int(w * rx), int(h * ry))], duration=100)
                time.sleep(1.5)
                if _find_element(self.driver, post_sel.next_button_selectors(), timeout=1.0):
                    return True
        except Exception:
            pass
        return True

    def _add_caption(self, caption: str, hashtags: List[str]) -> bool:
        """Add caption and hashtags."""
        try:
            # Combine caption and hashtags
            full_text = caption
            if hashtags:
                hashtag_str = " ".join(hashtags)
                full_text = f"{caption}\n\n{hashtag_str}" if caption else hashtag_str
            
            if not full_text:
                return True  # No caption to add
            
            # Find caption input with longer timeout
            el = _find_element(self.driver, post_sel.caption_input_selectors(), timeout=10.0)
            if el:
                try:
                    el.clear()
                    el.send_keys(full_text)
                    time.sleep(1)
                    logger.info("Added caption (%s chars)", len(full_text))
                    return True
                except Exception as send_error:
                    # Try alternative: tap and use ADB input
                    logger.warning("send_keys failed, trying tap + ADB input: %s", send_error)
                    try:
                        el.click()
                        time.sleep(0.5)
                        # Use ADB to input text (respects adb_serial); space as %s for shell
                        escaped_text = full_text.replace("\n", " ").replace(" ", "%s")[:500]
                        self._adb_cmd(["shell", "input", "text", escaped_text], timeout=5)
                        logger.info("Added caption via ADB input")
                        return True
                    except Exception as adb_error:
                        logger.error("ADB input also failed: %s", adb_error)
                        return False
            
            logger.warning("Caption input field not found")
            return False
        except Exception as e:
            logger.error("Failed to add caption: %s", e)
            return False
    
    def _tap_share(self) -> bool:
        """Tap Share/Post button."""
        try:
            el = _find_element(self.driver, post_sel.share_post_button_selectors(), timeout=5.0)
            if el:
                _tap_element(self.driver, el)
                time.sleep(3)  # Wait for post to process
                logger.info("Tapped share button")
                return True
            return False
        except Exception as e:
            logger.error("Failed to tap share: %s", e)
            return False

    def _advance_composer_then_share_and_verify(
        self, caption: str, hashtags: List[str], max_steps: int = 18
    ) -> bool:
        """
        Advance through crop/edit/caption screens until SHARE_READY, then add caption,
        tap share, and verify we're on SUCCESS or PROFILE. Only returns True when
        we've confirmed the post went through (avoids false positive on crop screen).
        """
        for step in range(max_steps):
            state = get_posting_screen_state(self.driver)
            if state == PostingScreenState.SUCCESS:
                return True
            if state == PostingScreenState.PROFILE:
                return True
            if state == PostingScreenState.SHARE_READY:
                self._add_caption(caption, hashtags)
                time.sleep(1)
                if not self._tap_share():
                    return False
                time.sleep(8)
                state_after = get_posting_screen_state(self.driver)
                if state_after in (PostingScreenState.SUCCESS, PostingScreenState.PROFILE):
                    return True
                return False
            if state in (PostingScreenState.CROP_OR_EDIT, PostingScreenState.CAPTION_SCREEN):
                # Tap Next/Skip only; do not tap Share here (crop/caption can be intermediate)
                el = find_element_by_intent(self.driver, "next_or_skip")
                if el and _tap_element_robust(self.driver, el):
                    time.sleep(2)
                else:
                    self._fallback_tap_for_state(PostingScreenState.CROP_OR_EDIT)
                    time.sleep(2)
                continue
            time.sleep(1.5)
        return False

    def _fallback_tap_for_state(self, state: PostingScreenState) -> bool:
        """Position-based fallback tap when find_element_by_intent returns None or when stuck."""
        try:
            size = self.driver.get_window_size()
            w, h = size["width"], size["height"]
            if state == PostingScreenState.PROFILE:
                x, y = int(w * 0.12), int(h * 0.08)
            elif state == PostingScreenState.CREATE_POST_FIRST_MENU:
                # Post option often center of bottom sheet
                x, y = w // 2, int(h * 0.4)
            elif state == PostingScreenState.CREATE_POST_MENU:
                # Gallery/Photo often at center or left-center of bottom sheet
                x, y = int(w * 0.5), int(h * 0.35)
            elif state == PostingScreenState.GALLERY:
                # First image in grid: upper-left area of content
                x, y = int(w * 0.2), int(h * 0.35)
            elif state == PostingScreenState.CROP_OR_EDIT:
                # Try bottom-right first (common for Next), then center-bottom (Continue)
                for rx, ry in [(0.9, 0.92), (0.5, 0.92), (0.85, 0.88)]:
                    x, y = int(w * rx), int(h * ry)
                    try:
                        self.driver.tap([(x, y)], duration=120)
                        time.sleep(STEP_SLEEP_SEC)
                        return True
                    except Exception:
                        continue
                return False
            elif state == PostingScreenState.SHARE_READY:
                # Share/Post button: try several positions (layout varies)
                for x_ratio, y_ratio in [(0.85, 0.08), (0.5, 0.92), (0.85, 0.5), (0.9, 0.12)]:
                    x, y = int(w * x_ratio), int(h * y_ratio)
                    try:
                        self.driver.tap([(x, y)], duration=150)
                        time.sleep(STEP_SLEEP_SEC)
                        return True
                    except Exception:
                        continue
                return False
            else:
                return False
            self.driver.tap([(x, y)], duration=100)
            time.sleep(STEP_SLEEP_SEC)
            return True
        except Exception as e:
            logger.debug("Fallback tap failed: %s", e)
            return False

    def _perform_action(self, state: PostingScreenState, caption: str, hashtags: List[str]) -> bool:
        """Perform the action for current state. Returns True if an action was executed."""
        action = get_action_for_state(state)
        logger.info("State=%s action=%s", state.value, action)

        if state == PostingScreenState.SUCCESS or action == "done":
            return True

        if action == "tap_create_post":
            el = find_element_by_intent(self.driver, "create_post")
            if not el:
                el = self._find_create_post_button_on_profile()
            if el and _tap_element_robust(self.driver, el):
                time.sleep(STEP_SLEEP_SEC)
                return True
            return self._fallback_tap_for_state(state)

        if action == "tap_post_option":
            el = find_element_by_intent(self.driver, "post_option")
            if el and _tap_element_robust(self.driver, el):
                time.sleep(STEP_SLEEP_SEC)
                return True
            return self._fallback_tap_for_state(PostingScreenState.CREATE_POST_FIRST_MENU)

        if action == "tap_gallery_or_photo":
            el = find_element_by_intent(self.driver, "gallery_or_photo")
            if el and _tap_element_robust(self.driver, el):
                time.sleep(STEP_SLEEP_SEC)
                return True
            return self._fallback_tap_for_state(PostingScreenState.CREATE_POST_MENU)

        if action == "tap_first_image":
            el = find_element_by_intent(self.driver, "first_image")
            if el and _tap_element_robust(self.driver, el):
                time.sleep(STEP_SLEEP_SEC)
                return True
            return self._fallback_tap_for_state(PostingScreenState.GALLERY)

        if action == "tap_next_or_skip":
            el = find_element_by_intent(self.driver, "next_or_skip")
            if el and _tap_element_robust(self.driver, el):
                time.sleep(STEP_SLEEP_SEC)
                return True
            return self._fallback_tap_for_state(state)

        if action == "fill_caption_then_share":
            if caption or hashtags:
                full_text = caption
                if hashtags:
                    full_text = f"{caption}\n\n{' '.join(hashtags)}" if caption else " ".join(hashtags)
                el = find_element_by_intent(self.driver, "caption_input")
                if el:
                    try:
                        el.clear()
                        el.send_keys(full_text)
                        time.sleep(1)
                    except Exception:
                        try:
                            el.click()
                            time.sleep(0.5)
                            escaped = full_text.replace(" ", "%s").replace("'", "\\'")[:500]
                            self._adb_cmd(["shell", "input", "text", escaped], timeout=5)
                        except Exception:
                            pass
            el = find_element_by_intent(self.driver, "share")
            if el and _tap_element_robust(self.driver, el):
                time.sleep(3)
                return True
            return self._fallback_tap_for_state(PostingScreenState.SHARE_READY)

        if action == "tap_share":
            el = find_element_by_intent(self.driver, "share")
            if el and _tap_element_robust(self.driver, el):
                time.sleep(3)
                return True
            return self._fallback_tap_for_state(state)

        if action == "retry_or_fallback":
            time.sleep(1)
            return False
        return False

    def post_photo(self, file_path: Path, caption: str = "", hashtags: Optional[List[str]] = None) -> bool:
        """Post a single photo using state-machine: see -> decide -> act until SUCCESS or fail."""
        hashtags = hashtags or []
        logger.info("Posting photo (state machine): %s", file_path.name)

        try:
            device_path = self._push_file_to_device(file_path)
            if not device_path:
                logger.error("Failed to push file to device")
                return False

            from src.device.instagram_app import InstagramApp
            app = InstagramApp(self.driver)
            # Close any open overlay/dialog, then go to Profile
            self._dismiss_overlays(back_presses=3)
            time.sleep(1)
            if not app.go_to_profile_tab():
                logger.error("Failed to open Profile tab")
                return False
            time.sleep(2)

            # Pre-flight: verify we're on a known starting screen
            initial_state = get_posting_screen_state(self.driver)
            if initial_state not in (
                PostingScreenState.PROFILE,
                PostingScreenState.CREATE_POST_MENU,
                PostingScreenState.CREATE_POST_FIRST_MENU,
            ):
                logger.warning("After Profile nav, state=%s; retrying go_to_profile_tab once", initial_state.value)
                if app.go_to_profile_tab():
                    time.sleep(2)
                else:
                    logger.warning("Pre-flight retry failed, continuing anyway")

            unknown_count = 0
            last_state = None
            same_state_count = 0
            last_action_was_share = False
            had_share_ready_before = False  # Track if we were ever on share screen (for success inference)

            for step in range(MAX_POST_STEPS):
                state = get_posting_screen_state(self.driver)
                logger.info("Step %d: state=%s", step + 1, state.value)

                if state == PostingScreenState.SHARE_READY:
                    had_share_ready_before = True

                if state == PostingScreenState.SUCCESS:
                    logger.info("Post success detected (explicit success state)")
                    return True

                # After we tapped Share, if we're now on Profile, the post was published and app went back
                if state == PostingScreenState.PROFILE and last_action_was_share and had_share_ready_before:
                    logger.info("Post success detected (returned to Profile after Share)")
                    return True

                if state == PostingScreenState.UNKNOWN:
                    unknown_count += 1
                    if unknown_count >= UNKNOWN_STEPS_BEFORE_FAIL:
                        logger.error("Stuck in UNKNOWN for %d steps", UNKNOWN_STEPS_BEFORE_FAIL)
                        try:
                            self.driver.save_screenshot("post_failed_unknown.png")
                            logger.info("Screenshot saved: post_failed_unknown.png")
                        except Exception:
                            pass
                        return False
                    time.sleep(1)
                    continue
                unknown_count = 0

                # Stuck in same state: dump screen for debugging, then try fallback tap
                skip_action = False
                if state == last_state:
                    same_state_count += 1
                    if same_state_count >= 2:
                        logger.warning("Stuck in %s for %d steps, trying fallback tap", state.value, same_state_count)
                        try:
                            dump_screen_summary(self.driver, f"post_stuck_{state.value}.txt")
                            logger.info("Screen dump saved for debugging")
                        except Exception as dump_err:
                            logger.debug("Screen dump failed: %s", dump_err)
                        if self._fallback_tap_for_state(state):
                            time.sleep(2.5)
                            new_after_fallback = get_posting_screen_state(self.driver)
                            if new_after_fallback == PostingScreenState.SUCCESS:
                                logger.info("Post success detected after fallback tap")
                                return True
                            last_state = new_after_fallback
                            skip_action = True
                        same_state_count = 0
                else:
                    same_state_count = 0
                    last_state = state

                if skip_action:
                    acted = False
                    time.sleep(STEP_SLEEP_SEC)
                else:
                    acted = self._perform_action(state, caption, hashtags)
                action_name = get_action_for_state(state)
                last_action_was_share = acted and action_name in ("tap_share", "fill_caption_then_share")

                # Wait for transition; longer after Share (upload + possible navigation back to Profile)
                if last_action_was_share:
                    time.sleep(8.0)
                else:
                    time.sleep(STEP_SLEEP_SEC)

                if not acted and state not in (PostingScreenState.CAPTION_SCREEN, PostingScreenState.SHARE_READY):
                    if self._fallback_tap_for_state(state):
                        time.sleep(2.0)
                    else:
                        logger.warning("No action and no fallback for state=%s", state.value)

                new_state = get_posting_screen_state(self.driver)
                if new_state == PostingScreenState.SUCCESS:
                    logger.info("Post success detected after action")
                    return True
                if last_action_was_share and new_state == PostingScreenState.PROFILE:
                    logger.info("Post success detected (Profile after Share)")
                    return True
            logger.error("Max steps (%d) reached without SUCCESS", MAX_POST_STEPS)
            try:
                self.driver.save_screenshot("post_failed_max_steps.png")
                logger.info("Screenshot saved: post_failed_max_steps.png")
            except Exception:
                pass
            return False
        except Exception as e:
            logger.error("Failed to post photo: %s", e, exc_info=True)
            try:
                self.driver.save_screenshot("post_failed_exception.png")
            except Exception:
                pass
            return False
    
    def post_video(self, file_path: Path, caption: str = "", hashtags: Optional[List[str]] = None) -> bool:
        """Post a video."""
        hashtags = hashtags or []
        logger.info("Posting video: %s", file_path.name)
        
        try:
            device_path = self._push_file_to_device(file_path)
            if not device_path:
                return False
            
            if not self._navigate_to_create_post():
                return False
            
            if not self._select_media_type(MediaType.VIDEO):
                return False
            
            if not self._select_file_from_gallery(file_path):
                return False
            
            # Wait for video processing, then advance through crop/edit to share and verify
            time.sleep(3)
            if self._advance_composer_then_share_and_verify(caption, hashtags):
                logger.info("Video posted successfully")
                return True
            return False
        except Exception as e:
            logger.error("Failed to post video: %s", e, exc_info=True)
            return False
    
    def post_reel(self, file_path: Path, caption: str = "", hashtags: Optional[List[str]] = None) -> bool:
        """Post a reel."""
        hashtags = hashtags or []
        logger.info("Posting reel: %s", file_path.name)
        
        try:
            device_path = self._push_file_to_device(file_path)
            if not device_path:
                return False
            
            if not self._navigate_to_create_post():
                return False
            
            if not self._select_media_type(MediaType.REEL):
                return False
            
            if not self._select_file_from_gallery(file_path):
                return False
            
            # Reels have multiple steps (crop, cover, music, etc.). Advance to share screen and verify.
            time.sleep(2)
            if self._advance_composer_then_share_and_verify(caption, hashtags):
                logger.info("Reel posted successfully")
                return True
            return False
        except Exception as e:
            logger.error("Failed to post reel: %s", e, exc_info=True)
            return False
    
    def post_carousel(self, file_paths: List[Path], caption: str = "", hashtags: Optional[List[str]] = None) -> bool:
        """Post a carousel (multiple images). Phase 1: pick all photos. Phase 2: crop/caption/share."""
        hashtags = hashtags or []
        logger.info("Posting carousel: %s images", len(file_paths))
        
        try:
            # Push all files to device
            device_paths = []
            for fp in file_paths:
                dp = self._push_file_to_device(fp)
                if dp:
                    device_paths.append(dp)
            
            if not device_paths:
                return False
            
            if not self._navigate_to_create_post():
                return False
            
            if not self._select_media_type(MediaType.PHOTO):  # Carousel uses photo flow
                return False
            
            # Phase 1: Select all photos first (with retries and Back-on-mistouch fallback)
            if not self._select_all_carousel_photos(file_paths):
                logger.error("Carousel: failed to select all photos")
                return False
            
            # Phase 2: Proceed to crop/edit -> caption -> share, and verify success
            time.sleep(1.5)
            if self._advance_composer_then_share_and_verify(caption, hashtags, max_steps=25):
                logger.info("Carousel posted successfully")
                return True
            return False
        except Exception as e:
            logger.error("Failed to post carousel: %s", e, exc_info=True)
            return False
