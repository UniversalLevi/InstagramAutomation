"""
TikTok warm-up planner: day bands, SCROLL_FYP, LIKE_VIDEO, VISIT_PROFILE, GO_TO_OWN_PROFILE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional


class ActionType(str, Enum):
    SCROLL_FYP = "scroll_fyp"
    LIKE_VIDEO = "like_video"
    VISIT_PROFILE = "visit_profile"
    RETURN_HOME = "return_home"
    GO_TO_OWN_PROFILE = "go_to_own_profile"
    IDLE = "idle"


@dataclass
class DayBand:
    min_days: int
    max_days: int
    scroll_min_sec: int
    scroll_max_sec: int
    profiles_min: int
    profiles_max: int
    likes_min: int
    likes_max: int


DEFAULT_DAY_BANDS = [
    DayBand(1, 3, 30, 60, 1, 1, 0, 1),
    DayBand(4, 7, 30, 60, 2, 3, 1, 2),
    DayBand(8, 14, 30, 60, 3, 4, 2, 3),
    DayBand(15, 9999, 30, 60, 2, 4, 1, 3),
]


@dataclass
class ActionPlanItem:
    action: ActionType
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DailyPlan:
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
    in_cooldown: bool,
    config: Dict[str, Any],
) -> Optional[DailyPlan]:
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

    if days_since_first < 14:
        max_likes = min(band.likes_max, max_likes_first_two_weeks - likes_today)
    else:
        max_likes = band.likes_max
    max_likes = max(0, max_likes)
    remaining_actions = max(0, max_actions_per_day - total_actions_today)

    warmup_cfg = config.get("warmup", {})
    fyp_scroll_count = warmup_cfg.get("fyp_scroll_count", 3)
    like_count = warmup_cfg.get("like_count", 4)
    visit_profile_count = warmup_cfg.get("visit_profile_count", 2)

    items: List[ActionPlanItem] = []

    items.append(ActionPlanItem(ActionType.SCROLL_FYP, {"num_videos": fyp_scroll_count}))

    num_likes = min(like_count, max_likes)
    for i in range(num_likes):
        items.append(ActionPlanItem(ActionType.LIKE_VIDEO, {}))
        if i < num_likes - 1:
            items.append(ActionPlanItem(ActionType.SCROLL_FYP, {"num_videos": fyp_scroll_count}))

    num_profiles = min(visit_profile_count, band.profiles_max, max(0, remaining_actions - len(items) - 2))
    for _ in range(num_profiles):
        items.append(ActionPlanItem(ActionType.VISIT_PROFILE, {}))
        items.append(ActionPlanItem(ActionType.RETURN_HOME, {}))

    items.append(ActionPlanItem(ActionType.GO_TO_OWN_PROFILE, {}))

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
