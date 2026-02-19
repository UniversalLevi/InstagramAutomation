"""
Instagram Android app selectors. Prefer accessibility id / content-desc; fallbacks for UI changes.
Retry-friendly: callers should retry with short waits when elements are missing.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

# Appium locator strategies
BY_ACCESSIBILITY_ID = "accessibility id"
BY_ID = "id"
BY_XPATH = "xpath"
BY_CLASS = "class name"

# --- Home / Feed ---
# Bottom nav: Home, Search, Reels, Shop, Profile
# Accessibility ids vary by locale; resource-id often contains "tab" or "bottom_navigation"

def home_tab_selectors() -> List[Tuple[str, str]]:
    """Locators for Home tab (feed). Try in order."""
    return [
        (BY_XPATH, "//*[contains(@content-desc, 'Home') or contains(@content-desc, 'home')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'tab_bar') and contains(@content-desc, 'Home')]"),
        (BY_ACCESSIBILITY_ID, "Home"),
    ]


def feed_recycler_selectors() -> List[Tuple[str, str]]:
    """Main feed list (RecyclerView or similar)."""
    return [
        (BY_XPATH, "//androidx.recyclerview.widget.RecyclerView"),
        (BY_XPATH, "//android.widget.ListView"),
        (BY_CLASS, "androidx.recyclerview.widget.RecyclerView"),
    ]


# --- Profile (from feed: tap avatar/username) ---
def profile_username_in_feed_selectors() -> List[Tuple[str, str]]:
    """Username or avatar in feed post header (to open profile)."""
    return [
        (BY_XPATH, "//*[contains(@resource-id, 'row_feed_photo_profile_name')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'row_feed_textview_username')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'username')]"),
        # Avatar/Profile picture
        (BY_XPATH, "//android.widget.ImageView[contains(@content-desc, 'profile picture')]"),
        (BY_XPATH, "//android.widget.ImageView[contains(@content-desc, 'Profile picture')]"),
        # Username text in post header
        (BY_XPATH, "//androidx.recyclerview.widget.RecyclerView//android.widget.TextView[@clickable='true'][1]"),
        (BY_XPATH, "//android.widget.LinearLayout[.//android.widget.ImageView]/android.widget.TextView[@clickable='true']"),
    ]


# --- Like button ---
def like_button_selectors() -> List[Tuple[str, str]]:
    """Like (heart) button on a post."""
    return [
        (BY_ACCESSIBILITY_ID, "Like"),
        (BY_XPATH, "//*[@content-desc='Like' or @content-desc='like']"),
        (BY_XPATH, "//*[contains(@content-desc, 'Like') and not(contains(@content-desc, 'Liked'))]"),
        (BY_XPATH, "//*[contains(@resource-id, 'like')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'double_tap')]"),
        # Try finding ImageView with heart icon
        (BY_XPATH, "//android.widget.ImageView[contains(@content-desc, 'Like')]"),
        # Generic: find clickable elements in post area
        (BY_XPATH, "//androidx.recyclerview.widget.RecyclerView//android.widget.ImageView[@clickable='true'][1]"),
    ]


def like_button_liked_selectors() -> List[Tuple[str, str]]:
    """Like button in liked state (to detect already liked)."""
    return [
        (BY_ACCESSIBILITY_ID, "Liked"),
        (BY_XPATH, "//*[@content-desc='Liked' or @content-desc='Unlike']"),
        (BY_XPATH, "//*[contains(@content-desc, 'Liked')]"),
        (BY_XPATH, "//*[contains(@content-desc, 'Unlike')]"),
    ]


# --- Search ---
def search_tab_selectors() -> List[Tuple[str, str]]:
    return [
        (BY_ACCESSIBILITY_ID, "Search"),
        (BY_XPATH, "//*[contains(@content-desc, 'Search') or contains(@content-desc, 'search')]"),
    ]


def search_edit_text_selectors() -> List[Tuple[str, str]]:
    """Search input field."""
    return [
        (BY_XPATH, "//*[contains(@resource-id, 'search') and (@class='android.widget.EditText' or @clickable='true')]"),
        (BY_CLASS, "android.widget.EditText"),
    ]


# --- Reels tab ---
def reels_tab_selectors() -> List[Tuple[str, str]]:
    """Locators for Reels tab."""
    return [
        (BY_ACCESSIBILITY_ID, "Reels"),
        (BY_XPATH, "//*[contains(@content-desc, 'Reels') or contains(@content-desc, 'reels')]"),
        (BY_XPATH, "//*[contains(@resource-id, 'tab_bar') and contains(@content-desc, 'Reels')]"),
    ]


# --- Profile tab (own profile) ---
def profile_tab_selectors() -> List[Tuple[str, str]]:
    return [
        (BY_ACCESSIBILITY_ID, "Profile"),
        (BY_XPATH, "//*[contains(@content-desc, 'Profile') or contains(@content-desc, 'profile')]"),
    ]


# --- Back / navigation ---
def back_button_selectors() -> List[Tuple[str, str]]:
    return [
        (BY_ACCESSIBILITY_ID, "Back"),
        (BY_XPATH, "//*[contains(@content-desc, 'Back') or contains(@content-desc, 'back')]"),
        (BY_XPATH, "//android.widget.ImageButton"),
    ]


# --- Health / block detection ---
def block_warning_selectors() -> List[Tuple[str, str]]:
    """Elements that indicate action blocked or warning."""
    return [
        (BY_XPATH, "//*[contains(@text, 'Try again later') or contains(@text, 'try again later')]"),
        (BY_XPATH, "//*[contains(@text, 'Action blocked') or contains(@text, 'action blocked')]"),
        (BY_XPATH, "//*[contains(@text, 'Suspicious') or contains(@text, 'suspicious')]"),
        (BY_XPATH, "//*[contains(@text, 'Challenge') or contains(@text, 'challenge')]"),
    ]


def get_first_selector_pair(selectors: List[Tuple[str, str]]) -> Optional[Tuple[str, str]]:
    return selectors[0] if selectors else None
