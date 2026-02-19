"""
Warm-up runner: execute DailyPlan via TikTokApp, record to state.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from src.device.tiktok_app import TikTokApp
from src.orchestrator.planner import ActionPlanItem, ActionType, DailyPlan
from src.randomization.engine import (
    maybe_do_nothing,
    maybe_exit_early,
    random_delay,
    random_scroll_duration,
    shuffle_actions,
)

logger = logging.getLogger(__name__)

DEFAULT_DELAY_MIN = 3
DEFAULT_DELAY_MAX = 40
DEFAULT_IDLE_SEC = 3


def run_plan(
    plan: DailyPlan,
    app: TikTokApp,
    account_id: str,
    run_date: date,
    *,
    on_action_done: Optional[Callable[[str, int], None]] = None,
    delay_between_actions: Optional[float] = None,
    delay_range: Optional[tuple] = None,
    session_started_at: Optional[datetime] = None,
    db_path: Optional[Path] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> dict:
    from state import repository as repo

    config = config or {}
    warmup_cfg = config.get("warmup", {})
    dmin = warmup_cfg.get("delay_between_actions_min", DEFAULT_DELAY_MIN)
    dmax = warmup_cfg.get("delay_between_actions_max", DEFAULT_DELAY_MAX)
    if delay_range:
        dmin, dmax = delay_range[0], delay_range[1]
    scroll_min = warmup_cfg.get("scroll_duration_min_sec", 30)
    scroll_max = warmup_cfg.get("scroll_duration_max_sec", 60)
    exit_early_prob = warmup_cfg.get("exit_early_probability", 0.05)
    if config.get("force_mode", False):
        exit_early_prob = 0.0

    session_started_at = session_started_at or datetime.now(timezone.utc)
    total_actions = 0
    likes_count = 0
    stopped_early = False
    max_session_sec = plan.max_session_minutes * 60

    items = list(plan.items)
    own_profile_items = [item for item in items if item.action == ActionType.GO_TO_OWN_PROFILE]
    other_items = [item for item in items if item.action != ActionType.GO_TO_OWN_PROFILE]
    items = shuffle_actions(other_items) + own_profile_items
    logger.info("Plan has %s actions: %s", len(items), [item.action.value for item in items])

    def elapsed() -> float:
        return (datetime.now(timezone.utc) - session_started_at).total_seconds()

    def should_stop() -> bool:
        if stop_flag and stop_flag():
            return True
        if elapsed() >= max_session_sec:
            return True
        return False

    def delay():
        if delay_between_actions is not None:
            time.sleep(delay_between_actions)
        else:
            random_delay(dmin, dmax)

    for item in items:
        if should_stop():
            stopped_early = True
            break
        if exit_early_prob > 0 and maybe_exit_early(exit_early_prob):
            logger.info("Exit early (random)")
            stopped_early = True
            break
        if app.has_block_warning():
            from src.health.monitor import set_cooldown
            health_cfg = config.get("health", {})
            set_cooldown(
                account_id,
                health_cfg.get("cooldown_days_min", 3),
                health_cfg.get("cooldown_days_max", 7),
                "block",
                db_path,
            )
            logger.warning("Block/warning detected; cooldown set. Stopping.")
            stopped_early = True
            break

        action = item.action
        params = item.params or {}

        if action == ActionType.SCROLL_FYP:
            num_videos = params.get("num_videos", 5)
            logger.info("Executing SCROLL_FYP - %s videos", num_videos)
            if app.go_to_home_tab():
                n = app.scroll_fyp_for_videos(num_videos, step_sec=2.0)
                total_actions += 1
                if on_action_done:
                    on_action_done("scroll_fyp", n)
                logger.info("scroll_fyp done, videos=%s", n)
            else:
                logger.warning("Failed to go to Home for scroll_fyp")
            delay()

        elif action == ActionType.LIKE_VIDEO:
            if likes_count >= plan.max_likes:
                logger.info("Skipping LIKE_VIDEO - at max (%s)", plan.max_likes)
                delay()
                continue
            if maybe_do_nothing(0.2):
                logger.info("Skipping LIKE_VIDEO (random)")
                delay()
                continue
            logger.info("Executing LIKE_VIDEO (%s/%s)", likes_count + 1, plan.max_likes)
            if app.go_to_home_tab():
                time.sleep(2.0)
                if app.like_current_video():
                    likes_count += 1
                    total_actions += 1
                    if on_action_done:
                        on_action_done("like_video", 1)
                    logger.info("like_video done")
                else:
                    logger.warning("Failed to like video")
            else:
                logger.warning("Failed to go to Home for like_video")
            delay()

        elif action == ActionType.VISIT_PROFILE:
            if maybe_do_nothing(0.1):
                logger.info("Skipping VISIT_PROFILE (random)")
                delay()
                continue
            logger.info("Executing VISIT_PROFILE")
            if app.go_to_home_tab():
                time.sleep(0.5)
                if app.visit_profile_from_feed():
                    total_actions += 1
                    if on_action_done:
                        on_action_done("visit_profile", 1)
                    logger.info("visit_profile done")
                else:
                    logger.warning("Failed to open profile from feed")
            else:
                app.tap_back()
                time.sleep(1.0)
                if app.go_to_home_tab() and app.visit_profile_from_feed():
                    total_actions += 1
                    if on_action_done:
                        on_action_done("visit_profile", 1)
            delay()

        elif action == ActionType.RETURN_HOME:
            logger.info("Executing RETURN_HOME")
            if app.tap_back():
                total_actions += 1
                if on_action_done:
                    on_action_done("return_home", 1)
            delay()

        elif action == ActionType.GO_TO_OWN_PROFILE:
            logger.info("Executing GO_TO_OWN_PROFILE")
            if app.go_to_profile_tab():
                total_actions += 1
                if on_action_done:
                    on_action_done("go_to_own_profile", 1)
                logger.info("go_to_own_profile done")
            else:
                logger.warning("Failed to go to profile tab")
            delay()

        elif action == ActionType.IDLE:
            time.sleep(params.get("duration_sec", DEFAULT_IDLE_SEC))
            if on_action_done:
                on_action_done("idle", 1)

        else:
            delay()

    session_ended_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    session_started_str = session_started_at.isoformat() + "Z"
    repo.upsert_daily_totals(
        account_id,
        run_date,
        total_actions,
        likes_count,
        session_started_at=session_started_str,
        session_ended_at=session_ended_at,
        db_path=db_path,
    )
    return {
        "total_actions": total_actions,
        "likes_count": likes_count,
        "stopped_early": stopped_early,
    }
