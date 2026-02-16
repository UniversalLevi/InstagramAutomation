"""
Selectors for Instagram posting UI elements.
"""
from __future__ import annotations

from typing import List, Tuple

# Appium locator strategies
BY_ACCESSIBILITY_ID = "accessibility id"
BY_ID = "id"
BY_XPATH = "xpath"
BY_CLASS = "class name"


def create_post_button_selectors() -> List[Tuple[str, str]]:
    """Create post button (+ icon) - generic (feed tab bar or elsewhere)."""
    return [
        (BY_ACCESSIBILITY_ID, "New post"),
        (BY_ACCESSIBILITY_ID, "New Post"),
        (BY_ACCESSIBILITY_ID, "Create"),
        (BY_XPATH, "//*[contains(@content-desc, 'New post') or contains(@content-desc, 'new post')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Create')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'tab_bar')]//*[contains(@content-desc, 'New')]"),
        (BY_XPATH, "//android.widget.ImageButton[contains(@content-desc, 'New')]"),
        (BY_XPATH, "//android.widget.ImageButton[contains(@content-desc, 'Create')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'tab_bar')]//android.widget.ImageButton[position()=3]"),
    ]


def create_post_button_on_profile_selectors() -> List[Tuple[str, str]]:
    """Create post (+) button on Profile screen - usually top left in the action bar."""
    return [
        (BY_ACCESSIBILITY_ID, "New post"),
        (BY_ACCESSIBILITY_ID, "New Post"),
        (BY_ACCESSIBILITY_ID, "Create"),
        (BY_XPATH, "//*[contains(@content-desc, 'New post') or contains(@content-desc, 'new post')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Create') or contains(@content-desc, 'create')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Add') or contains(@content-desc, 'add')]"),
        # Top action bar: first ImageButton is often the + on profile
        (BY_XPATH, "//*[contains(@resource-id, 'action_bar')]//android.widget.ImageButton[1]"),
        (BY_XPATH, "//*[contains(@resource-id, 'toolbar')]//android.widget.ImageButton[1]"),
        (BY_XPATH, "//*[contains(@resource-id, 'action_bar')]//android.widget.ImageView[1]"),
        (BY_XPATH, "//android.widget.ImageButton[contains(@content-desc, 'New')]"),
        (BY_XPATH, "//android.widget.ImageButton[contains(@content-desc, 'Create')]"),
        (BY_XPATH, "//android.widget.ImageView[contains(@content-desc, 'New')]"),
        (BY_XPATH, "//android.widget.ImageView[contains(@content-desc, 'Create')]"),
    ]


def gallery_selectors() -> List[Tuple[str, str]]:
    """Gallery/file picker button."""
    return [
        (BY_XPATH, "//*[contains(@content-desc, 'Gallery') or contains(@content-desc, 'gallery')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'gallery')]"),
        (BY_XPATH, "//*[contains(@text, 'Gallery')]"),
    ]


def photo_selectors() -> List[Tuple[str, str]]:
    """Photo option in create post menu."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Photo') or contains(@text, 'photo')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Photo')]"),
    ]


def video_selectors() -> List[Tuple[str, str]]:
    """Video option in create post menu."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Video') or contains(@text, 'video')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Video')]"),
    ]


def reel_selectors() -> List[Tuple[str, str]]:
    """Reel option in create post menu."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Reel') or contains(@text, 'reel')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Reel')]"),
    ]


def post_option_selectors() -> List[Tuple[str, str]]:
    """Post option in the first create menu (Post | Story | Reel | Live)."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Post') and not(contains(@text, 'Story'))]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Post') and not(contains(@content-desc, 'Story'))]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Post')]"),
    ]


def next_button_selectors() -> List[Tuple[str, str]]:
    """Next/Continue button (crop and composer steps)."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Next') or contains(@text, 'next')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Next')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'next')]"),
        (BY_XPATH, "//*[contains(@text, 'Continue') or contains(@text, 'continue')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Continue')]"),
    ]


def continue_button_selectors() -> List[Tuple[str, str]]:
    """Continue / Proceed button (crop or intermediate steps)."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Continue') or contains(@text, 'continue')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Continue')]"),
        (BY_XPATH, "//*[contains(@text, 'Proceed') or contains(@text, 'proceed')]"),
    ]


def caption_input_selectors() -> List[Tuple[str, str]]:
    """Caption text input field."""
    return [
        (BY_XPATH, "//*[contains(@resource-id, 'caption')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'row_caption')]//android.widget.EditText"),
        (BY_XPATH, "//android.widget.EditText[contains(@hint, 'Write a caption') or contains(@hint, 'caption')]"),
        (BY_CLASS, "android.widget.EditText"),
    ]


def share_post_button_selectors() -> List[Tuple[str, str]]:
    """Share/Post button."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Share') or contains(@text, 'Post')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Share') or contains(@content-desc, 'Post')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'share') or contains(@resource-id, 'post')]"),
    ]


def add_more_selectors() -> List[Tuple[str, str]]:
    """Add more photos button (for carousel)."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Add more') or contains(@text, 'add more')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Add more')]"),
        (BY_XPATH, "//*[contains(@text, 'Add photo') or contains(@text, 'Add')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Add')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'add')]"),
    ]


def done_button_selectors() -> List[Tuple[str, str]]:
    """Done button (after selecting media)."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Done') or contains(@text, 'done')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Done')]"),
    ]


def filter_selectors() -> List[Tuple[str, str]]:
    """Filter button (optional, can skip)."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Filter') or contains(@text, 'filter')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Filter')]"),
    ]


def skip_button_selectors() -> List[Tuple[str, str]]:
    """Skip button (for optional steps)."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Skip') or contains(@text, 'skip')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Skip')]"),
    ]
