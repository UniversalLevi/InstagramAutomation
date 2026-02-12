"""
Orchestrator: decide what to do today based on account age, daily caps, and health.
Output: action plan (or no action). No automated login; one session per day.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

# Action types allowed by spec
class ActionType(str, Enum):
    SCROLL_FEED = "scroll_feed"
    SCROLL_REELS = "scroll_reels"  # Scroll in Reels section
    VISIT_PROFILE = "visit_profile"
    LIKE_POST = "like_post"
    LIKE_REEL = "like_reel"  # Like a Reel video
    RETURN_HOME = "return_home"
    GO_TO_OWN_PROFILE = "go_to_own_profile"
    IDLE = "idle"
    SEARCH_HASHTAG = "search_hashtag"  # rare, optional
    BIO_EDIT = "bio_edit"  # once in day 8-14


@dataclass
class DayBand:
    """Warm-up phase by days since first run."""
    min_days: int
    max_days: int
    scroll_min_sec: int
    scroll_max_sec: int
    profiles_min: int
    profiles_max: int
    likes_min: int
    likes_max: int
    search_hashtag: bool
    bio_edit_allowed: bool


# From plan: Day 1-3, 4-7, 8-14, 15+
# Reduced scroll durations for faster warmup (30-60 sec instead of 120-240)
DEFAULT_DAY_BANDS = [
    DayBand(1, 3, 30, 60, 1, 1, 0, 1, False, False),
    DayBand(4, 7, 30, 60, 2, 3, 1, 2, True, False),
    DayBand(8, 14, 30, 60, 3, 4, 2, 3, True, True),
    DayBand(15, 9999, 30, 60, 2, 4, 1, 3, True, False),
]


@dataclass
class ActionPlanItem:
    action: ActionType
    # Optional params (e.g. scroll_sec for SCROLL_FEED)
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DailyPlan:
    """Plan for one session: ordered list of actions (order will be shuffled by randomization layer)."""
    items: List[ActionPlanItem]
    max_session_minutes: int
    max_total_actions: int
    max_likes: int


def _band_for_day(days_since_first: int, bands: Optional[List[DayBand]] = None) -> DayBand:
    bands = bands or DEFAULT_DAY_BANDS
    for b in bands:
        if b.min_days <= days_since_first <= b.max_days:
            return b
    return bands[-1]


def build_plan(
    first_run_date: date,
    last_run_date: Optional[date],
    today: date,
    total_actions_today: int,
    likes_today: int,
    bio_edit_done: bool,
    in_cooldown: bool,
    config: Dict[str, Any],
) -> Optional[DailyPlan]:
    """
    Build today's plan or return None (e.g. already ran today, or in cooldown).
    Enforces: one session per day, max actions, max likes (first 2 weeks), max session minutes.
    """
    if in_cooldown:
        return None

    limits = config.get("limits", {})
    one_session_per_day = limits.get("one_session_per_day", True)
    max_actions_per_day = limits.get("max_actions_per_day", 10)
    max_likes_first_two_weeks = limits.get("max_likes_per_day_first_two_weeks", 5)
    max_session_minutes = limits.get("max_session_minutes", 15)

    if one_session_per_day and last_run_date == today:
        return None

    days_since_first = (today - first_run_date).days
    band = _band_for_day(days_since_first)

    # Cap likes for first 14 days
    if days_since_first < 14:
        max_likes = min(band.likes_max, max_likes_first_two_weeks - likes_today)
    else:
        max_likes = band.likes_max
    max_likes = max(0, max_likes)

    # How many actions we can still do
    remaining_actions = max(0, max_actions_per_day - total_actions_today)

    items: List[ActionPlanItem] = []

    # Go to Reels and scroll through videos first
    items.append(ActionPlanItem(ActionType.SCROLL_REELS, {"num_videos": 3}))  # Initial scroll
    
    # Randomly like 3-4 Reels (scattered throughout scrolling)
    # Target 3-4 Reel likes, but adjust if max_likes is lower
    if max_likes >= 4:
        num_reel_likes = 4
    elif max_likes >= 3:
        num_reel_likes = 3
    else:
        num_reel_likes = max_likes  # Use whatever we have
    for i in range(num_reel_likes):
        items.append(ActionPlanItem(ActionType.LIKE_REEL, {}))
        # After each like (except last), scroll to next video
        if i < num_reel_likes - 1:
            items.append(ActionPlanItem(ActionType.SCROLL_REELS, {"num_videos": 2}))  # Scroll 2 videos between likes

    # Visit profiles (reduced since we're focusing on Reels)
    num_profiles = min(band.profiles_max - 1, remaining_actions - len(items) - 2)
    num_profiles = max(0, num_profiles)  # Can be 0 if we're focusing on Reels
    for _ in range(num_profiles):
        items.append(ActionPlanItem(ActionType.VISIT_PROFILE, {}))
        items.append(ActionPlanItem(ActionType.RETURN_HOME, {}))

    # Regular post likes (very limited, reduced since we have Reel likes)
    remaining_post_likes = max(0, max_likes - num_reel_likes)
    for _ in range(remaining_post_likes):
        items.append(ActionPlanItem(ActionType.LIKE_POST, {}))

    # Go to own profile
    items.append(ActionPlanItem(ActionType.GO_TO_OWN_PROFILE, {}))

    # One bio edit only in day 8-14, once ever
    if band.bio_edit_allowed and not bio_edit_done:
        items.append(ActionPlanItem(ActionType.BIO_EDIT, {}))

    # Cap total items by remaining actions and rough session length
    items = items[: max_session_minutes * 2]
    if remaining_actions < len(items):
        items = items[: remaining_actions]

    max_likes_cap = max_likes_first_two_weeks if days_since_first < 14 else 5
    return DailyPlan(
        items=items,
        max_session_minutes=max_session_minutes,
        max_total_actions=max_actions_per_day,
        max_likes=max_likes_cap,
    )


def get_days_since_first(first_run_date: Optional[date], today: Optional[date] = None) -> int:
    if not first_run_date:
        return 0
    today = today or date.today()
    return (today - first_run_date).days
