"""
Screen state detection and find-by-intent for Instagram posting flow.
See -> Decide -> Act: this module provides "see" (state) and "decide" (find element by intent).
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Success phrases in page source (lowercase) to confirm post was shared
SUCCESS_PHRASES = [
    "your post has been shared",
    "post shared",
    "shared to your",
]


class PostingScreenState(str, Enum):
    PROFILE = "profile"
    CREATE_POST_FIRST_MENU = "create_post_first_menu"  # Post | Story | Reel | Live
    CREATE_POST_MENU = "create_post_menu"  # Gallery | Photo (after tapping Post)
    GALLERY = "gallery"
    CROP_OR_EDIT = "crop_or_edit"
    CAPTION_SCREEN = "caption_screen"
    SHARE_READY = "share_ready"
    SUCCESS = "success"
    UNKNOWN = "unknown"


def _find_el(driver, selectors: List[Tuple[str, str]], timeout: float = 1.5):
    """Thin wrapper to avoid circular import; use instagram_app._find_element."""
    from src.device.instagram_app import _find_element
    return _find_element(driver, selectors, timeout=timeout)


def get_posting_screen_state(driver) -> PostingScreenState:
    """
    Detect current screen state using priority order.
    Uses lightweight checks: key element lookups and a slice of page_source.
    """
    try:
        # Cache page source once per detection (first 12k chars so toasts are found)
        try:
            full_src = driver.page_source or ""
            src_lower = full_src[:12000].lower()
        except Exception:
            src_lower = ""

        # 1) SUCCESS: explicit success phrases (toast or screen text)
        for phrase in SUCCESS_PHRASES:
            if phrase in src_lower:
                return PostingScreenState.SUCCESS

        # 2) SHARE_READY: Share/Post button visible AND caption area present, AND no "Next" (so not crop/edit)
        from src.device import post_selectors as post_sel
        share_el = _find_el(driver, post_sel.share_post_button_selectors(), timeout=0.8)
        caption_el_for_share = _find_el(driver, post_sel.caption_input_selectors(), timeout=0.5)
        next_el_for_share = _find_el(driver, post_sel.next_button_selectors(), timeout=0.4)
        if share_el and caption_el_for_share and not next_el_for_share:
            return PostingScreenState.SHARE_READY

        # 3) CAPTION_SCREEN: EditText with caption hint or resource-id
        caption_el = _find_el(driver, post_sel.caption_input_selectors(), timeout=0.8)
        if caption_el:
            return PostingScreenState.CAPTION_SCREEN

        # 4) CROP_OR_EDIT: Next button visible (and we're not on caption)
        next_el = _find_el(driver, post_sel.next_button_selectors(), timeout=0.8)
        if next_el:
            return PostingScreenState.CROP_OR_EDIT

        # 5) PROFILE (before CREATE menus so we prefer it when both could match)
        from src.device import selectors as sel
        create_on_profile = _find_el(driver, post_sel.create_post_button_on_profile_selectors(), timeout=0.5)
        if create_on_profile:
            return PostingScreenState.PROFILE
        profile_tab = _find_el(driver, sel.profile_tab_selectors(), timeout=0.5)
        if profile_tab:
            return PostingScreenState.PROFILE

        # 6) GALLERY: picker with images; exclude when create menu options (Photo/Reel) visible
        photo_el = _find_el(driver, post_sel.photo_selectors(), timeout=0.4)
        reel_el = _find_el(driver, post_sel.reel_selectors(), timeout=0.4)
        gallery_el = _find_el(driver, post_sel.gallery_selectors(), timeout=0.5)
        if not photo_el and not reel_el:
            if gallery_el:
                return PostingScreenState.GALLERY
            if "gallery" in src_lower or "recent" in src_lower:
                try:
                    from appium.webdriver.common.appiumby import AppiumBy
                    images = driver.find_elements(AppiumBy.XPATH, "//android.widget.ImageView")
                    if len(images) >= 4 and "recycler" in (driver.page_source or "").lower()[:3000]:
                        return PostingScreenState.GALLERY
                except Exception:
                    pass

        # 7) CREATE_POST_FIRST_MENU: Post | Story | Reel (no Gallery option yet)
        if "story" in src_lower and "reel" in src_lower and not gallery_el:
            return PostingScreenState.CREATE_POST_FIRST_MENU

        # 8) CREATE_POST_MENU: Gallery/Photo/Reel options (second step)
        if photo_el or gallery_el or reel_el:
            return PostingScreenState.CREATE_POST_MENU

    except Exception as e:
        logger.debug("get_posting_screen_state error: %s", e)

    return PostingScreenState.UNKNOWN


def get_action_for_state(state: PostingScreenState) -> str:
    """Return the next action name for the given state (for post_photo goal)."""
    return {
        PostingScreenState.PROFILE: "tap_create_post",
        PostingScreenState.CREATE_POST_FIRST_MENU: "tap_post_option",
        PostingScreenState.CREATE_POST_MENU: "tap_gallery_or_photo",
        PostingScreenState.GALLERY: "tap_first_image",
        PostingScreenState.CROP_OR_EDIT: "tap_next_or_skip",
        PostingScreenState.CAPTION_SCREEN: "fill_caption_then_share",
        PostingScreenState.SHARE_READY: "fill_caption_then_share",
        PostingScreenState.SUCCESS: "done",
        PostingScreenState.UNKNOWN: "retry_or_fallback",
    }.get(state, "retry_or_fallback")


def find_element_by_intent(driver, intent: str):
    """
    Find the best-matching visible element for the given intent.
    intents: create_post, gallery_or_photo, first_image, next_or_skip, caption_input, share
    Returns WebElement or None.
    """
    from appium.webdriver.common.appiumby import AppiumBy
    from src.device import post_selectors as post_sel
    from src.device.instagram_app import _find_element

    if intent == "create_post":
        el = _find_element(driver, post_sel.create_post_button_on_profile_selectors(), timeout=2.0)
        return el

    if intent == "post_option":
        return _find_element(driver, post_sel.post_option_selectors(), timeout=1.5)

    if intent == "gallery_or_photo":
        # Prefer clickable, reasonably sized elements (exclude tiny tab bar icons)
        def _best_gallery_or_photo():
            for selectors in [post_sel.gallery_selectors(), post_sel.photo_selectors()]:
                try:
                    by_map = {"accessibility id": AppiumBy.ACCESSIBILITY_ID, "id": AppiumBy.ID,
                              "xpath": AppiumBy.XPATH, "class name": AppiumBy.CLASS_NAME}
                    for by_key, locator in selectors:
                        by = by_map.get(by_key, by_key)
                        els = driver.find_elements(by, locator)
                        for el in els:
                            try:
                                if not el.is_displayed():
                                    continue
                                clickable = el.get_attribute("clickable") == "true"
                                sz = el.size
                                if sz and sz.get("width", 0) * sz.get("height", 0) < 400:
                                    continue  # skip very small
                                if clickable:
                                    return el
                            except Exception:
                                continue
                        for el in els:
                            try:
                                if el.is_displayed():
                                    return el
                            except Exception:
                                continue
                except Exception:
                    continue
            return None
        el = _best_gallery_or_photo()
        if el:
            return el
        el = _find_element(driver, post_sel.gallery_selectors(), timeout=1.0)
        if el:
            return el
        return _find_element(driver, post_sel.photo_selectors(), timeout=1.0)

    if intent == "first_image":
        for xpath in [
            "//android.widget.ImageView[@clickable='true'][1]",
            "//androidx.recyclerview.widget.RecyclerView//android.widget.ImageView[1]",
            "//android.widget.ImageView[1]",
        ]:
            try:
                el = driver.find_element(AppiumBy.XPATH, xpath)
                if el and el.is_displayed():
                    return el
            except Exception:
                continue
        return None

    if intent == "next_or_skip":
        for selectors in [
            post_sel.next_button_selectors(),
            post_sel.continue_button_selectors(),
            post_sel.done_button_selectors(),
            post_sel.skip_button_selectors(),
        ]:
            el = _find_element(driver, selectors, timeout=0.8)
            if el:
                return el
        return None

    if intent == "caption_input":
        return _find_element(driver, post_sel.caption_input_selectors(), timeout=2.0)

    if intent == "share":
        # Prefer composer Share button (top area), not tab bar "Post" (bottom)
        try:
            from appium.webdriver.common.appiumby import AppiumBy
            size = driver.get_window_size()
            h = size.get("height", 800)
            tab_bar_y_max = int(h * 0.85)  # Tab bar usually in bottom 15%
            by_map = {"accessibility id": AppiumBy.ACCESSIBILITY_ID, "id": AppiumBy.ID,
                      "xpath": AppiumBy.XPATH, "class name": AppiumBy.CLASS_NAME}
            for by_key, locator in post_sel.share_post_button_selectors():
                try:
                    by = by_map.get(by_key, by_key)
                    els = driver.find_elements(by, locator)
                    for el in els:
                        if not el.is_displayed():
                            continue
                        try:
                            loc = el.location
                            el_center_y = loc.get("y", 0) + (el.size.get("height", 0) // 2)
                            if el_center_y < tab_bar_y_max:
                                return el  # Above tab bar = composer Share
                        except Exception:
                            pass
                    # If none above tab bar, return first visible (fallback)
                    for el in els:
                        if el.is_displayed():
                            return el
                except Exception:
                    continue
        except Exception:
            pass
        return _find_element(driver, post_sel.share_post_button_selectors(), timeout=2.0)

    return None


def dump_screen_summary(driver, path: Optional[str] = None) -> str:
    """
    Collect visible elements (content-desc, text, resource-id) and write to a debug file.
    Optionally saves a screenshot with the same base path and .png extension.
    Returns the path written (txt path).
    """
    import os
    out_path = path or "post_debug_screen.txt"
    lines = []
    try:
        try:
            full_src = driver.page_source or ""
            lines.append("=== Page source (first 8000 chars) ===")
            lines.append(full_src[:8000])
            lines.append("")
        except Exception as e:
            lines.append("page_source error: " + str(e))
        try:
            from appium.webdriver.common.appiumby import AppiumBy
            # Android: content-desc, text, resource-id (get_attribute uses lowercase with hyphen)
            for attr in ["content-desc", "text", "resource-id"]:
                try:
                    els = driver.find_elements(AppiumBy.XPATH, "//*")
                    lines.append(f"=== Elements with {attr} (max 80) ===")
                    count = 0
                    for el in els:
                        if count >= 80:
                            break
                        try:
                            if not el.is_displayed():
                                continue
                            val = el.get_attribute(attr) if hasattr(el, "get_attribute") else None
                            if not val or not str(val).strip():
                                continue
                            rid = el.get_attribute("resource-id") if hasattr(el, "get_attribute") else ""
                            lines.append(f"  {count}: {str(val)[:80]}  [resource-id={rid}]")
                            count += 1
                        except Exception:
                            continue
                    lines.append("")
                except Exception as e:
                    lines.append(f"{attr} error: " + str(e))
        except Exception as e:
            lines.append("element scan error: " + str(e))
        with open(out_path, "w", encoding="utf-8", errors="replace") as f:
            f.write("\n".join(lines))
        logger.info("Screen dump saved: %s", out_path)
        base = os.path.splitext(out_path)[0]
        try:
            driver.save_screenshot(base + ".png")
            logger.info("Screenshot saved: %s.png", base)
        except Exception as e:
            logger.debug("Screenshot failed: %s", e)
    except Exception as e:
        logger.warning("dump_screen_summary failed: %s", e)
        out_path = ""
    return out_path
