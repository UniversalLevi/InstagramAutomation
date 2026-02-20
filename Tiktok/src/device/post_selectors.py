"""
Selectors for TikTok posting (create) flow: +, Upload, gallery, Next, caption, Post.
"""
from __future__ import annotations

from typing import List, Tuple

BY_ACCESSIBILITY_ID = "accessibility id"
BY_ID = "id"
BY_XPATH = "xpath"
BY_CLASS = "class name"


def create_post_button_selectors() -> List[Tuple[str, str]]:
    """Create (+) button - center of bottom nav or on create screen."""
    return [
        (BY_ACCESSIBILITY_ID, "Create"),
        (BY_XPATH, "//*[contains(@content-desc, 'Create') or contains(@content-desc, 'create')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'create') or contains(@resource-id, 'post')]"),
        (BY_XPATH, "//android.widget.ImageButton[contains(@content-desc, 'Create')]"),
    ]


def create_post_button_on_profile_selectors() -> List[Tuple[str, str]]:
    """Same as create - TikTok uses same + for create from anywhere."""
    return create_post_button_selectors()


def upload_selectors() -> List[Tuple[str, str]]:
    """Upload option (to pick from gallery) - icon to the right of record button."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Upload') or contains(@text, 'upload')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Upload') or contains(@content-desc, 'upload')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Gallery') or contains(@content-desc, 'gallery')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'album') or contains(@content-desc, 'library') or contains(@content-desc, 'photo')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'upload')]"),
        (BY_XPATH, "//*[contains(@text, 'Gallery') or contains(@text, 'gallery')]"),
        # Create screen: clickable image/button in bottom area (upload icon often has no text)
        (BY_XPATH, "//*[@clickable='true' and (contains(@resource-id, 'upload') or contains(@resource-id, 'gallery') or contains(@resource-id, 'album') or contains(@resource-id, 'choose') or contains(@resource-id, 'media'))]"),
    ]


def gallery_selectors() -> List[Tuple[str, str]]:
    """Gallery / file picker."""
    return [
        (BY_XPATH, "//*[contains(@content-desc, 'Gallery') or contains(@content-desc, 'gallery')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'gallery')]"),
        (BY_XPATH, "//*[contains(@text, 'Gallery') or contains(@text, 'Recent')]"),
    ]


def next_button_selectors() -> List[Tuple[str, str]]:
    """Next / Continue (trim and composer steps)."""
    return [
        (BY_ID, "com.zhiliaoapp.musically:id/vn0"),
        (BY_XPATH, "//*[contains(@text, 'Next') or contains(@text, 'next')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Next')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'next')]"),
        (BY_XPATH, "//*[contains(@text, 'Continue') or contains(@text, 'continue')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Continue')]"),
    ]


def continue_button_selectors() -> List[Tuple[str, str]]:
    return [
        (BY_XPATH, "//*[contains(@text, 'Continue') or contains(@text, 'continue')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Continue')]"),
    ]


def caption_input_selectors() -> List[Tuple[str, str]]:
    """Caption / description input."""
    return [
        (BY_XPATH, "//*[contains(@resource-id, 'caption')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'desc')]//android.widget.EditText"),
        (BY_XPATH, "//android.widget.EditText[contains(@hint, 'caption') or contains(@hint, 'description') or contains(@hint, 'Add a caption')]"),
        (BY_CLASS, "android.widget.EditText"),
    ]


def share_post_button_selectors() -> List[Tuple[str, str]]:
    """Post / Publish button."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Post') or contains(@text, 'post')]"),
        (BY_XPATH, "//*[contains(@text, 'Publish') or contains(@text, 'publish')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Post') or contains(@content-desc, 'Publish')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'post') or contains(@resource-id, 'publish')]"),
    ]


def done_button_selectors() -> List[Tuple[str, str]]:
    """Done (after selecting media)."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Done') or contains(@text, 'done')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Done')]"),
    ]


def skip_button_selectors() -> List[Tuple[str, str]]:
    return [
        (BY_XPATH, "//*[contains(@text, 'Skip') or contains(@text, 'skip')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Skip')]"),
    ]
