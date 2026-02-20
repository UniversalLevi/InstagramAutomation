"""
Screen state detection for TikTok posting flow. See -> Decide -> Act.
Uses visible hints (text, resource-id) so we judge by what's on screen, not just selectors.
"""
from __future__ import annotations

import logging
import re
from enum import Enum
from typing import List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

SUCCESS_PHRASES = [
    "posted",
    "post shared",
    "your video has been posted",
    "video posted",
    "your video is now live",
    "video is now live",
]

# Resource-id that means we're inside the create/record flow (not profile).
CREATE_FLOW_ROOT_ID = "video_record_new_scene_root"


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


def get_visible_hints(driver) -> Set[str]:
    """Collect visible text and resource-id tokens from the screen (lowercase)."""
    hints: Set[str] = set()
    try:
        full_src = driver.page_source or ""
        # Resource ids: musically:id/xxx -> add "xxx"
        for m in re.finditer(r"resource-id=\"[^\"]*?([a-z0-9_]+)\"", full_src, re.I):
            hints.add(m.group(1).lower())
        # Visible text from text="..."
        for m in re.finditer(r"text=\"([^\"]+)\"", full_src):
            t = m.group(1).strip().lower()
            if len(t) <= 50 and t not in ("null", ""):
                hints.add(t)
        # content-desc
        for m in re.finditer(r"content-desc=\"([^\"]+)\"", full_src):
            t = m.group(1).strip().lower()
            if len(t) <= 50 and t not in ("null", ""):
                hints.add(t)
    except Exception as e:
        logger.debug("get_visible_hints error: %s", e)
    return hints


def get_posting_screen_state(driver) -> PostingScreenState:
    """
    Prefer screen-driven state: use visible hints first, then element selectors.
    If we're inside create flow (video_record_new_scene_root), never return PROFILE.
    """
    try:
        try:
            full_src = driver.page_source or ""
            src_lower = full_src[:16000].lower()
        except Exception:
            src_lower = ""

        hints = get_visible_hints(driver)
        in_create_flow = CREATE_FLOW_ROOT_ID in src_lower or "video_record_new_scene_root" in hints

        # 1) Success
        for phrase in SUCCESS_PHRASES:
            if phrase in src_lower:
                return PostingScreenState.SUCCESS

        # 2) Share-ready: Post button + caption area; avoid create-menu "POST" tab
        from src.device import post_selectors as post_sel
        share_el = _find_el(driver, post_sel.share_post_button_selectors(), timeout=0.6)
        caption_el = _find_el(driver, post_sel.caption_input_selectors(), timeout=0.5)
        create_menu_tabs = ("create", "photo", "text", "60s", "10m", "15s")  # trim/create flow
        if share_el and caption_el:
            next_el = _find_el(driver, post_sel.next_button_selectors(), timeout=0.3)
            if not next_el and not any(x in hints for x in create_menu_tabs):
                return PostingScreenState.SHARE_READY
        if "post" in hints and any(x in hints for x in ("caption", "desc", "add a caption")):
            if not any(x in hints for x in create_menu_tabs):
                return PostingScreenState.SHARE_READY

        # 3) Caption screen (caption field visible, no share button)
        if caption_el and not share_el:
            return PostingScreenState.CAPTION_SCREEN

        # 4) Inside create flow: decide by hints and elements (never PROFILE here)
        if in_create_flow:
            next_el = _find_el(driver, post_sel.next_button_selectors(), timeout=0.6)
            done_el = _find_el(driver, post_sel.done_button_selectors(), timeout=0.4)
            # Gallery picker: Next visible but "Select multiple" means we must select a video first
            if "select multiple" in hints and (next_el or "next" in hints):
                return PostingScreenState.GALLERY
            # Next / Done / Continue visible -> trim or gallery confirm step (no select multiple)
            if next_el or done_el or "next" in hints or "done" in hints or "continue" in hints:
                return PostingScreenState.TRIM_EDIT
            # Gallery: Recents, Videos, Photos (no Next yet)
            if any(x in hints for x in ("recents", "videos", "photos", "all ", "ai gallery")):
                return PostingScreenState.GALLERY
            # Upload / Gallery / Add sound -> create menu (tabs)
            if any(x in hints for x in ("upload", "add sound", "music", "gallery")):
                return PostingScreenState.CREATE_MENU
            # CREATE/POST/PHOTO/TEXT tabs but no Next -> create menu
            if any(x in hints for x in ("create", "photo", "text")):
                return PostingScreenState.CREATE_MENU
            # Fallback for create flow
            upload_el = _find_el(driver, post_sel.upload_selectors(), timeout=0.4)
            gallery_el = _find_el(driver, post_sel.gallery_selectors(), timeout=0.4)
            if upload_el or gallery_el:
                return PostingScreenState.CREATE_MENU
            return PostingScreenState.CREATE_MENU

        # 5) Not in create flow: profile vs create menu (first time)
        next_el = _find_el(driver, post_sel.next_button_selectors(), timeout=0.5)
        if next_el:
            return PostingScreenState.TRIM_EDIT

        upload_el = _find_el(driver, post_sel.upload_selectors(), timeout=0.4)
        gallery_el = _find_el(driver, post_sel.gallery_selectors(), timeout=0.5)
        if upload_el or gallery_el:
            return PostingScreenState.CREATE_MENU

        if "gallery" in src_lower or "recent" in src_lower:
            try:
                from appium.webdriver.common.appiumby import AppiumBy
                images = driver.find_elements(AppiumBy.XPATH, "//android.widget.ImageView")
                if len(images) >= 4:
                    return PostingScreenState.GALLERY
            except Exception:
                pass

        # 6) Profile: only when we're clearly not in create flow
        create_btn = _find_el(driver, post_sel.create_post_button_on_profile_selectors(), timeout=0.5)
        if create_btn and not in_create_flow:
            return PostingScreenState.PROFILE
        try:
            from src.device import selectors as sel
            profile_tab = _find_el(driver, sel.profile_tab_selectors(), timeout=0.5)
            if profile_tab and not in_create_flow:
                return PostingScreenState.PROFILE
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


def get_suggested_action_from_hints(driver) -> Optional[str]:
    """
    Decide next action from what's visible on screen (text/ids).
    Returns intent string: tap_next, tap_upload, tap_create_post, tap_first_video, fill_caption_then_share, None.
    """
    hints = get_visible_hints(driver)
    try:
        full_src = driver.page_source or ""
        src_lower = full_src[:12000].lower()
    except Exception:
        src_lower = ""

    in_create_flow = CREATE_FLOW_ROOT_ID in src_lower

    # Share-ready: Post button visible (avoid create-menu "POST" tab)
    create_tabs = ("create", "photo", "60s", "10m", "15s")
    if ("post" in hints or "publish" in hints) and not any(x in hints for x in create_tabs):
        from src.device import post_selectors as post_sel
        share_el = _find_el(driver, post_sel.share_post_button_selectors(), timeout=0.5)
        if share_el:
            return "fill_caption_then_share"

    # Next / gallery actions only when inside create flow (avoid wrong hint on profile)
    if in_create_flow:
        # Next / Done / Continue -> tap next
        if "next" in hints or "done" in hints or "continue" in hints:
            return "tap_next_or_skip"
        # Gallery: Recents, Videos, Photos -> tap first video or Next
        if any(x in hints for x in ("select multiple", "recents", "videos", "photos")):
            from src.device import post_selectors as post_sel
            next_el = _find_el(driver, post_sel.next_button_selectors(), timeout=0.5)
            if next_el:
                return "tap_next_or_skip"
            return "tap_first_video"
        # Create menu: Upload, Add sound, CREATE tab
        if any(x in hints for x in ("upload", "add sound", "create", "photo", "text")):
            return "tap_upload"

    # Profile: only when not in create flow
    if not in_create_flow:
        return "tap_create_post"

    return None


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
