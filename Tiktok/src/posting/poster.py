"""
Appium-based TikTok posting. Video only. State machine: see -> decide -> act until SUCCESS or fail.
"""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import List, Optional

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.device import post_selectors as post_sel
from src.posting.models import MediaType, PostItem
from src.posting.screen_state import (
    PostingScreenState,
    get_posting_screen_state,
    get_action_for_state,
    get_suggested_action_from_hints,
    find_element_by_intent,
    dump_screen_summary,
)
from src.device.tiktok_app import _find_element, _tap_element, _tap_element_robust

logger = logging.getLogger(__name__)

MAX_POST_STEPS = 25
UNKNOWN_STEPS_BEFORE_FAIL = 4
STEP_SLEEP_SEC = 1.5


class TikTokPoster:
    """Handles posting video to TikTok via Appium."""

    def __init__(self, driver, account_id: str, adb_serial: Optional[str] = None):
        self.driver = driver
        self.account_id = account_id
        self.adb_serial = adb_serial

    def _adb_cmd(self, args: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        cmd = ["adb"]
        if self.adb_serial:
            cmd.extend(["-s", self.adb_serial])
        cmd.extend(args)
        return subprocess.run(cmd, capture_output=True, timeout=timeout)

    def post_item(self, post_item: PostItem) -> bool:
        if post_item.media_type != MediaType.VIDEO:
            logger.error("TikTok supports video only")
            return False
        return self.post_video(post_item.file_paths[0], post_item.caption, post_item.hashtags)

    def _dismiss_overlays(self, back_presses: int = 3) -> None:
        try:
            for i in range(back_presses):
                try:
                    self.driver.back()
                    time.sleep(0.8)
                except Exception:
                    break
            time.sleep(0.5)
        except Exception:
            pass

    def _navigate_to_create_post(self) -> bool:
        from src.device.tiktok_app import TikTokApp
        app = TikTokApp(self.driver)
        self._dismiss_overlays(back_presses=3)
        time.sleep(1)
        if not app.go_to_profile_tab():
            if not app.go_to_home_tab():
                logger.error("Failed to open Home or Profile")
                return False
        time.sleep(2)
        el = _find_element(self.driver, post_sel.create_post_button_selectors(), timeout=3.0)
        if el:
            _tap_element(self.driver, el)
            time.sleep(2)
            if _find_element(self.driver, post_sel.upload_selectors(), timeout=3.0) or _find_element(self.driver, post_sel.gallery_selectors(), timeout=2.0):
                return True
            return True
        try:
            size = self.driver.get_window_size()
            x = int(size["width"] * 0.5)
            y = int(size["height"] * 0.85)
            self.driver.tap([(x, y)], 100)
            time.sleep(2)
            if _find_element(self.driver, post_sel.upload_selectors(), timeout=2.0):
                return True
        except Exception:
            pass
        logger.error("Could not find create post button")
        return False

    def _push_file_to_device(self, file_path: Path) -> Optional[str]:
        device_dir = "/sdcard/DCIM/TikTokPost/"
        device_filename = file_path.name
        device_file_path = device_dir + device_filename
        try:
            self._adb_cmd(["shell", "mkdir", "-p", device_dir], timeout=10)
            result = self._adb_cmd(["push", str(file_path), device_file_path], timeout=60)
            if result.returncode != 0:
                logger.error("adb push failed: %s", (result.stderr or result.stdout or b"").decode(errors="replace"))
                return None
            logger.info("Pushed file to device: %s", device_file_path)
            check = self._adb_cmd(["shell", f"test -f '{device_file_path}' && echo exists"], timeout=10)
            if "exists" not in (check.stdout or b"").decode().strip():
                logger.error("File not found on device at %s", device_file_path)
                return None
            try:
                self._adb_cmd(["shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{device_file_path}"], timeout=5)
                time.sleep(1)
            except Exception:
                pass
            return device_file_path
        except subprocess.TimeoutExpired:
            logger.error("adb push timed out")
            return None
        except Exception as e:
            logger.error("Error pushing file: %s", e)
            return None

    def _tap_upload(self) -> bool:
        el = _find_element(self.driver, post_sel.upload_selectors(), timeout=3.0)
        if not el:
            el = _find_element(self.driver, post_sel.gallery_selectors(), timeout=2.0)
        if el:
            _tap_element(self.driver, el)
            time.sleep(2.5)
            return True
        return False

    def _select_video_from_gallery(self, file_path: Path) -> bool:
        gallery_el = _find_element(self.driver, post_sel.gallery_selectors(), timeout=4.0)
        if gallery_el:
            _tap_element(self.driver, gallery_el)
            time.sleep(2.5)
        else:
            time.sleep(1.5)
        from appium.webdriver.common.appiumby import AppiumBy
        for xpath in [
            "//android.widget.ImageView[@clickable='true'][1]",
            "//*[contains(@resource-id, 'thumbnail') or contains(@resource-id, 'video')][1]",
            "//androidx.recyclerview.widget.RecyclerView//android.widget.ImageView[1]",
            "//android.widget.ImageView[1]",
        ]:
            try:
                el = self.driver.find_element(AppiumBy.XPATH, xpath)
                if el and el.is_displayed():
                    el.click()
                    time.sleep(1.5)
                    if _find_element(self.driver, post_sel.next_button_selectors(), timeout=1.0) or _find_element(self.driver, post_sel.done_button_selectors(), timeout=1.0):
                        return True
                    return True
            except Exception:
                continue
        done_el = _find_element(self.driver, post_sel.done_button_selectors(), timeout=2.0)
        if done_el:
            _tap_element(self.driver, done_el)
            time.sleep(2)
            return True
        return False

    def _add_caption(self, caption: str, hashtags: List[str]) -> bool:
        full_text = caption
        if hashtags:
            hashtag_str = " ".join(hashtags)
            full_text = f"{caption}\n\n{hashtag_str}" if caption else hashtag_str
        if not full_text:
            return True
        el = _find_element(self.driver, post_sel.caption_input_selectors(), timeout=10.0)
        if el:
            try:
                el.clear()
                el.send_keys(full_text)
                time.sleep(1)
                logger.info("Added caption (%s chars)", len(full_text))
                return True
            except Exception:
                try:
                    el.click()
                    time.sleep(0.5)
                    escaped_text = full_text.replace("\n", " ").replace(" ", "%s")[:500]
                    self._adb_cmd(["shell", "input", "text", escaped_text], timeout=5)
                    return True
                except Exception:
                    return False
        return False

    def _tap_share(self) -> bool:
        el = _find_element(self.driver, post_sel.share_post_button_selectors(), timeout=5.0)
        if el:
            _tap_element(self.driver, el)
            time.sleep(3)
            logger.info("Tapped share button")
            return True
        return False

    def _advance_then_share_and_verify(self, caption: str, hashtags: List[str], max_steps: int = 18) -> bool:
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
            if state in (PostingScreenState.TRIM_EDIT, PostingScreenState.CAPTION_SCREEN):
                el = find_element_by_intent(self.driver, "next_or_skip")
                if el and _tap_element_robust(self.driver, el):
                    time.sleep(2)
                else:
                    try:
                        size = self.driver.get_window_size()
                        w, h = size["width"], size["height"]
                        self.driver.tap([(int(w * 0.9), int(h * 0.92))], 120)
                        time.sleep(2)
                    except Exception:
                        pass
                continue
            time.sleep(1.5)
        return False

    def _fallback_tap_for_state(self, state: PostingScreenState) -> bool:
        try:
            size = self.driver.get_window_size()
            w, h = size["width"], size["height"]
            if state == PostingScreenState.SHARE_READY:
                for rx, ry in [(0.85, 0.08), (0.5, 0.92), (0.85, 0.5)]:
                    self.driver.tap([(int(w * rx), int(h * ry))], 150)
                    time.sleep(STEP_SLEEP_SEC)
                    return True
            if state == PostingScreenState.TRIM_EDIT:
                self.driver.tap([(int(w * 0.9), int(h * 0.92))], 120)
                time.sleep(STEP_SLEEP_SEC)
                return True
            if state == PostingScreenState.CREATE_MENU:
                # Upload/gallery icon is to the right of the record button (bottom-right area)
                self.driver.tap([(int(w * 0.85), int(h * 0.88))], 120)
                time.sleep(STEP_SLEEP_SEC)
                return True
            if state == PostingScreenState.GALLERY:
                self.driver.tap([(int(w * 0.2), int(h * 0.35))], 100)
                time.sleep(STEP_SLEEP_SEC)
                return True
        except Exception as e:
            logger.debug("Fallback tap failed: %s", e)
        return False

    def _perform_action(
        self,
        state: PostingScreenState,
        caption: str,
        hashtags: List[str],
        suggested_intent: Optional[str] = None,
    ) -> bool:
        # Prefer screen-driven intent when available (see and judge)
        action = suggested_intent if suggested_intent else get_action_for_state(state)
        logger.info("State=%s action=%s%s", state.value, action, " (from hints)" if suggested_intent else "")
        if state == PostingScreenState.SUCCESS or action == "done":
            return True
        if action == "tap_create_post":
            el = find_element_by_intent(self.driver, "create_post")
            if el and _tap_element_robust(self.driver, el):
                time.sleep(STEP_SLEEP_SEC)
                return True
            return self._fallback_tap_for_state(state)
        if action == "tap_upload":
            el = find_element_by_intent(self.driver, "upload")
            if el and _tap_element_robust(self.driver, el):
                time.sleep(STEP_SLEEP_SEC)
                return True
            return self._fallback_tap_for_state(PostingScreenState.CREATE_MENU)
        if action == "tap_first_video":
            el = find_element_by_intent(self.driver, "first_video")
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
                            escaped = full_text.replace(" ", "%s").replace("'", "\\'")[:500]
                            self._adb_cmd(["shell", "input", "text", escaped], timeout=5)
                        except Exception:
                            pass
            el = find_element_by_intent(self.driver, "share")
            if el and _tap_element_robust(self.driver, el):
                time.sleep(3)
                return True
            return self._fallback_tap_for_state(PostingScreenState.SHARE_READY)
        if action == "retry_or_fallback":
            time.sleep(1)
            return False
        return False

    def post_video(self, file_path: Path, caption: str = "", hashtags: Optional[List[str]] = None) -> bool:
        hashtags = hashtags or []
        logger.info("Posting video (state machine): %s", file_path.name)
        try:
            device_path = self._push_file_to_device(file_path)
            if not device_path:
                logger.error("Failed to push file to device")
                return False
            from src.device.tiktok_app import TikTokApp
            app = TikTokApp(self.driver)
            self._dismiss_overlays(back_presses=3)
            time.sleep(1)
            if not app.go_to_profile_tab():
                if not app.go_to_home_tab():
                    logger.error("Failed to open Profile or Home")
                    return False
            time.sleep(2)
            initial_state = get_posting_screen_state(self.driver)
            if initial_state not in (PostingScreenState.PROFILE, PostingScreenState.CREATE_MENU):
                if app.go_to_profile_tab():
                    time.sleep(2)

            unknown_count = 0
            last_state = None
            same_state_count = 0
            last_action_was_share = False
            had_share_ready_before = False

            for step in range(MAX_POST_STEPS):
                state = get_posting_screen_state(self.driver)
                suggested_intent = get_suggested_action_from_hints(self.driver)
                # Trust state on profile: never use gallery/next hint when we're on profile
                if state == PostingScreenState.PROFILE and suggested_intent in ("tap_first_video", "tap_next_or_skip"):
                    suggested_intent = None
                logger.info("Step %d: state=%s%s", step + 1, state.value, f" hint={suggested_intent}" if suggested_intent else "")
                if state == PostingScreenState.SHARE_READY:
                    had_share_ready_before = True
                if state == PostingScreenState.SUCCESS:
                    logger.info("Post success detected")
                    return True
                if state == PostingScreenState.PROFILE and last_action_was_share and had_share_ready_before:
                    logger.info("Post success (returned to Profile after Share)")
                    return True
                if state == PostingScreenState.UNKNOWN:
                    # Use hint-driven action when state is unknown
                    if suggested_intent:
                        acted = self._perform_action(state, caption, hashtags, suggested_intent=suggested_intent)
                        if acted:
                            time.sleep(STEP_SLEEP_SEC)
                            new_state = get_posting_screen_state(self.driver)
                            if new_state == PostingScreenState.SUCCESS:
                                return True
                            last_state = new_state
                        time.sleep(STEP_SLEEP_SEC)
                        continue
                    unknown_count += 1
                    if unknown_count >= UNKNOWN_STEPS_BEFORE_FAIL:
                        logger.error("Stuck in UNKNOWN for %d steps", UNKNOWN_STEPS_BEFORE_FAIL)
                        try:
                            self.driver.save_screenshot("post_failed_unknown.png")
                        except Exception:
                            pass
                        return False
                    time.sleep(1)
                    continue
                unknown_count = 0

                skip_action = False
                if state == last_state:
                    same_state_count += 1
                    if same_state_count >= 2:
                        logger.warning("Stuck in %s, trying hint-driven then fallback", state.value)
                        try:
                            dump_screen_summary(self.driver, f"post_stuck_{state.value}.txt")
                        except Exception:
                            pass
                        # Stuck on TRIM_EDIT (gallery picker): select video first then Next
                        if state == PostingScreenState.TRIM_EDIT and (
                            suggested_intent == "tap_next_or_skip"
                            or get_action_for_state(state) == "tap_next_or_skip"
                        ):
                            self._perform_action(state, caption, hashtags, suggested_intent="tap_first_video")
                            time.sleep(2.0)
                            acted = self._perform_action(state, caption, hashtags, suggested_intent="tap_next_or_skip")
                            if acted:
                                time.sleep(2.5)
                                new_state = get_posting_screen_state(self.driver)
                                if new_state == PostingScreenState.SUCCESS:
                                    return True
                                last_state = new_state
                                skip_action = True
                        # Stuck on CREATE_MENU: tap upload icon by coordinates (right of record button)
                        if not skip_action and state == PostingScreenState.CREATE_MENU:
                            if self._fallback_tap_for_state(PostingScreenState.CREATE_MENU):
                                time.sleep(2.5)
                                new_state = get_posting_screen_state(self.driver)
                                if new_state != PostingScreenState.CREATE_MENU:
                                    last_state = new_state
                                    skip_action = True
                        # Prefer action from what's visible (Next, Upload, etc.)
                        if not skip_action and suggested_intent:
                            acted = self._perform_action(state, caption, hashtags, suggested_intent=suggested_intent)
                            if acted:
                                time.sleep(2.5)
                                new_state = get_posting_screen_state(self.driver)
                                if new_state == PostingScreenState.SUCCESS:
                                    return True
                                last_state = new_state
                                skip_action = True
                        if not skip_action and self._fallback_tap_for_state(state):
                            time.sleep(2.5)
                            new_state = get_posting_screen_state(self.driver)
                            if new_state == PostingScreenState.SUCCESS:
                                return True
                            last_state = new_state
                            skip_action = True
                        same_state_count = 0
                else:
                    same_state_count = 0
                    last_state = state

                if skip_action:
                    acted = False
                    time.sleep(STEP_SLEEP_SEC)
                else:
                    acted = self._perform_action(state, caption, hashtags, suggested_intent=suggested_intent)
                action_name = suggested_intent or get_action_for_state(state)
                last_action_was_share = acted and action_name in ("fill_caption_then_share",)

                if last_action_was_share:
                    time.sleep(8.0)
                    # Success-wait: poll for SUCCESS or PROFILE and return immediately
                    for _ in range(10):
                        state_after = get_posting_screen_state(self.driver)
                        if state_after == PostingScreenState.SUCCESS:
                            logger.info("Post success detected after share")
                            return True
                        if state_after == PostingScreenState.PROFILE:
                            logger.info("Post success (returned to Profile after Share)")
                            return True
                        time.sleep(2)
                else:
                    time.sleep(STEP_SLEEP_SEC)

                if not acted and state not in (PostingScreenState.CAPTION_SCREEN, PostingScreenState.SHARE_READY):
                    self._fallback_tap_for_state(state)
                    time.sleep(2.0)

                new_state = get_posting_screen_state(self.driver)
                if new_state == PostingScreenState.SUCCESS:
                    return True
                if last_action_was_share and new_state == PostingScreenState.PROFILE:
                    return True
            logger.error("Max steps (%d) reached", MAX_POST_STEPS)
            try:
                self.driver.save_screenshot("post_failed_max_steps.png")
            except Exception:
                pass
            return False
        except Exception as e:
            logger.error("Failed to post video: %s", e, exc_info=True)
            try:
                self.driver.save_screenshot("post_failed_exception.png")
            except Exception:
                pass
            return False
