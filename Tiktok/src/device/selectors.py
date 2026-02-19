"""
TikTok Android app selectors. Bottom nav: Home, Discover, + (Create), Inbox, Profile.
FYP (For You) scroll, like, profile visit. Refine with real device dumps.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

BY_ACCESSIBILITY_ID = "accessibility id"
BY_ID = "id"
BY_XPATH = "xpath"
BY_CLASS = "class name"


def home_tab_selectors() -> List[Tuple[str, str]]:
    """Home tab (For You feed)."""
    return [
        (BY_ACCESSIBILITY_ID, "Home"),
        (BY_XPATH, "//*[contains(@content-desc, 'Home') or contains(@content-desc, 'home')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'For You') or contains(@content-desc, 'For you')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'tab') and contains(@content-desc, 'Home')]"),
    ]


def discover_tab_selectors() -> List[Tuple[str, str]]:
    """Discover / Search tab."""
    return [
        (BY_ACCESSIBILITY_ID, "Discover"),
        (BY_XPATH, "//*[contains(@content-desc, 'Discover') or contains(@content-desc, 'discover')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Search')]"),
    ]


def create_tab_selectors() -> List[Tuple[str, str]]:
    """Create (+) button in bottom nav."""
    return [
        (BY_ACCESSIBILITY_ID, "Create"),
        (BY_XPATH, "//*[contains(@content-desc, 'Create') or contains(@content-desc, 'create')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Upload') or contains(@content-desc, 'upload')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'create') or contains(@resource-id, 'post')]"),
    ]


def inbox_tab_selectors() -> List[Tuple[str, str]]:
    """Inbox tab."""
    return [
        (BY_ACCESSIBILITY_ID, "Inbox"),
        (BY_XPATH, "//*[contains(@content-desc, 'Inbox') or contains(@content-desc, 'inbox')]"),
    ]


def profile_tab_selectors() -> List[Tuple[str, str]]:
    """Profile / Me tab (own profile)."""
    return [
        (BY_ACCESSIBILITY_ID, "Profile"),
        (BY_ACCESSIBILITY_ID, "Me"),
        (BY_XPATH, "//*[contains(@content-desc, 'Profile') or contains(@content-desc, 'profile')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Me') or contains(@content-desc, 'me')]"),
    ]


def like_button_selectors() -> List[Tuple[str, str]]:
    """Like (heart) on video."""
    return [
        (BY_ACCESSIBILITY_ID, "Like"),
        (BY_XPATH, "//*[contains(@content-desc, 'Like') and not(contains(@content-desc, 'Liked'))]"),
        (BY_XPATH, "//*[contains(@resource-id, 'like')]"),
        (BY_XPATH, "//android.widget.ImageView[contains(@content-desc, 'Like')]"),
    ]


def like_button_liked_selectors() -> List[Tuple[str, str]]:
    """Like button in liked state."""
    return [
        (BY_ACCESSIBILITY_ID, "Liked"),
        (BY_XPATH, "//*[contains(@content-desc, 'Liked') or contains(@content-desc, 'Unlike')]"),
    ]


def profile_username_in_feed_selectors() -> List[Tuple[str, str]]:
    """Username or avatar on current video to open creator profile."""
    return [
        (BY_XPATH, "//*[contains(@resource-id, 'username') or contains(@resource-id, 'author')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'profile') or contains(@content-desc, 'Profile')]"),
        (BY_XPATH, "//android.widget.TextView[@clickable='true']"),
    ]


def back_button_selectors() -> List[Tuple[str, str]]:
    return [
        (BY_ACCESSIBILITY_ID, "Back"),
        (BY_XPATH, "//*[contains(@content-desc, 'Back') or contains(@content-desc, 'back')]"),
        (BY_XPATH, "//android.widget.ImageButton"),
    ]


def block_warning_selectors() -> List[Tuple[str, str]]:
    """Block or rate-limit warning."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Try again later') or contains(@text, 'try again later')]"),
        (BY_XPATH, "//*[contains(@text, 'Action blocked') or contains(@text, 'action blocked')]"),
        (BY_XPATH, "//*[contains(@text, 'Suspicious') or contains(@text, 'suspicious')]"),
        (BY_XPATH, "//*[contains(@text, 'Challenge') or contains(@text, 'challenge')]"),
    ]


def get_first_selector_pair(selectors: List[Tuple[str, str]]) -> Optional[Tuple[str, str]]:
    return selectors[0] if selectors else None
