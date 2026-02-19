"""
Screen state detection for TikTok posting flow. See -> Decide -> Act.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

SUCCESS_PHRASES = [
    "posted",
    "post shared",
    "your video has been posted",
    "video posted",
]


class PostingScreenState(str, Enum):
    PROFILE = "profile"
    CREATE_MENU = "create_menu"   # After + : Upload / Camera etc
    GALLERY = "gallery"
    TRIM_EDIT = "trim_edit"
    CAPTION_SCREEN = "caption_screen"
    SHARE_READY = "share_ready"
    SUCCESS = "success"
    UNKNOWN = "unknown"


def _find_el(driver, selectors: List[Tuple[str, str]], timeout: float = 1.5):
    from src.device.tiktok_app import _find_element
    return _find_element(driver, selectors, timeout=timeout)


def get_posting_screen_state(driver) -> PostingScreenState:
    try:
        try:
            full_src = driver.page_source or ""
            src_lower = full_src[:12000].lower()
        except Exception:
            src_lower = ""

        for phrase in SUCCESS_PHRASES:
            if phrase in src_lower:
                return PostingScreenState.SUCCESS

        from src.device import post_selectors as post_sel
        share_el = _find_el(driver, post_sel.share_post_button_selectors(), timeout=0.8)
        caption_el = _find_el(driver, post_sel.caption_input_selectors(), timeout=0.5)
        next_el = _find_el(driver, post_sel.next_button_selectors(), timeout=0.4)
        if share_el and caption_el and not next_el:
            return PostingScreenState.SHARE_READY

        caption_el = _find_el(driver, post_sel.caption_input_selectors(), timeout=0.8)
        if caption_el:
            return PostingScreenState.CAPTION_SCREEN

        next_el = _find_el(driver, post_sel.next_button_selectors(), timeout=0.8)
        if next_el:
            return PostingScreenState.TRIM_EDIT

        create_btn = _find_el(driver, post_sel.create_post_button_on_profile_selectors(), timeout=0.5)
        if create_btn:
            return PostingScreenState.PROFILE
        from src.device import selectors as sel
        profile_tab = _find_el(driver, sel.profile_tab_selectors(), timeout=0.5)
        if profile_tab:
            return PostingScreenState.PROFILE

        upload_el = _find_el(driver, post_sel.upload_selectors(), timeout=0.4)
        gallery_el = _find_el(driver, post_sel.gallery_selectors(), timeout=0.5)
        if upload_el or gallery_el:
            return PostingScreenState.CREATE_MENU

        if gallery_el or "gallery" in src_lower or "recent" in src_lower:
            try:
                from appium.webdriver.common.appiumby import AppiumBy
                images = driver.find_elements(AppiumBy.XPATH, "//android.widget.ImageView")
                if len(images) >= 4:
                    return PostingScreenState.GALLERY
            except Exception:
                pass

        if upload_el or gallery_el:
            return PostingScreenState.CREATE_MENU
    except Exception as e:
        logger.debug("get_posting_screen_state error: %s", e)
    return PostingScreenState.UNKNOWN


def get_action_for_state(state: PostingScreenState) -> str:
    return {
        PostingScreenState.PROFILE: "tap_create_post",
        PostingScreenState.CREATE_MENU: "tap_upload",
        PostingScreenState.GALLERY: "tap_first_video",
        PostingScreenState.TRIM_EDIT: "tap_next_or_skip",
        PostingScreenState.CAPTION_SCREEN: "fill_caption_then_share",
        PostingScreenState.SHARE_READY: "fill_caption_then_share",
        PostingScreenState.SUCCESS: "done",
        PostingScreenState.UNKNOWN: "retry_or_fallback",
    }.get(state, "retry_or_fallback")


def find_element_by_intent(driver, intent: str):
    from appium.webdriver.common.appiumby import AppiumBy
    from src.device import post_selectors as post_sel
    from src.device.tiktok_app import _find_element

    if intent == "create_post":
        return _find_element(driver, post_sel.create_post_button_on_profile_selectors(), timeout=2.0)
    if intent == "upload":
        return _find_element(driver, post_sel.upload_selectors(), timeout=1.5)
    if intent == "first_video":
        for xpath in [
            "//android.widget.ImageView[@clickable='true'][1]",
            "//*[contains(@resource-id, 'thumbnail') or contains(@resource-id, 'video')][1]",
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
        return _find_element(driver, post_sel.share_post_button_selectors(), timeout=2.0)
    return None


def dump_screen_summary(driver, path: Optional[str] = None) -> str:
    import os
    out_path = path or "post_debug_screen.txt"
    lines = []
    try:
        try:
            full_src = driver.page_source or ""
            lines.append("=== Page source (first 8000 chars) ===")
            lines.append(full_src[:8000])
        except Exception as e:
            lines.append("page_source error: " + str(e))
        try:
            from appium.webdriver.common.appiumby import AppiumBy
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
            lines.append(f"element scan error: {e}")
        with open(out_path, "w", encoding="utf-8", errors="replace") as f:
            f.write("\n".join(lines))
        logger.info("Screen dump saved: %s", out_path)
        base = os.path.splitext(out_path)[0]
        try:
            driver.save_screenshot(base + ".png")
        except Exception:
            pass
    except Exception as e:
        logger.warning("dump_screen_summary failed: %s", e)
        out_path = ""
    return out_path
