"""
Warm-up runner: execute DailyPlan items via InstagramApp, record to state.
Uses randomization: shuffled order, random delays 3-40s, optional do-nothing/exit-early.
Enforces max session duration (~15 min).
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from src.device.instagram_app import InstagramApp
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
    app: InstagramApp,
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
    """
    Execute plan items (shuffled). Random delay between actions. Record via on_action_done.
    Returns dict with total_actions, likes_count, stopped_early.
    Caller must run from project root so "state" package is importable.
    """
    from state import repository as repo

    config = config or {}
    warmup_cfg = config.get("warmup", {})
    dmin = warmup_cfg.get("delay_between_actions_min", DEFAULT_DELAY_MIN)
    dmax = warmup_cfg.get("delay_between_actions_max", DEFAULT_DELAY_MAX)
    if delay_range:
        dmin, dmax = delay_range[0], delay_range[1]
    scroll_min = warmup_cfg.get("scroll_duration_min_sec", 120)
    scroll_max = warmup_cfg.get("scroll_duration_max_sec", 240)

    session_started_at = session_started_at or datetime.utcnow()
    total_actions = 0
    likes_count = 0
    stopped_early = False
    max_session_sec = plan.max_session_minutes * 60

    # Shuffle action order (no fixed sequence)
    items = shuffle_actions(plan.items)
    logger.info("Plan has %s actions: %s", len(items), [item.action.value for item in items])

    def elapsed() -> float:
        return (datetime.utcnow() - session_started_at).total_seconds()

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
        if maybe_exit_early(0.05):
            logger.info("Exit early (random)")
            stopped_early = True
            break
        # Health check: block/warning screen
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

        if action == ActionType.SCROLL_FEED:
            duration_sec = params.get("duration_sec") or random_scroll_duration(scroll_min, scroll_max)
            logger.info("Executing SCROLL_FEED for %s seconds", duration_sec)
            if app.go_to_home_tab():
                time.sleep(0.5)  # Reduced wait
                n = app.scroll_feed_for_seconds(duration_sec, step_sec=0.8)  # Faster scrolling (scrolls UP now)
                total_actions += 1
                if on_action_done:
                    on_action_done("scroll_feed", 1)
                logger.info("scroll_feed done, scrolls=%s", n)
            else:
                logger.warning("Failed to go to home tab for scroll_feed")
            delay()

        elif action == ActionType.SCROLL_REELS:
            num_videos = params.get("num_videos", 5)
            logger.info("Executing SCROLL_REELS - scrolling through %s videos", num_videos)
            if app.go_to_reels_tab():
                n = app.scroll_reels_for_videos(num_videos, step_sec=2.0)
                total_actions += 1
                if on_action_done:
                    on_action_done("scroll_reels", n)
                logger.info("scroll_reels done, videos scrolled=%s", n)
            else:
                logger.warning("Failed to go to Reels tab")
            delay()

        elif action == ActionType.LIKE_REEL:
            if likes_count >= plan.max_likes:
                logger.info("Skipping LIKE_REEL - already at max (%s)", plan.max_likes)
                delay()
                continue
            if maybe_do_nothing(0.2):  # 20% chance to skip (random behavior)
                logger.info("Skipping LIKE_REEL (random do-nothing)")
                delay()
                continue
            logger.info("Executing LIKE_REEL (%s/%s)", likes_count + 1, plan.max_likes)
            # Make sure we're in Reels
            if app.go_to_reels_tab():
                time.sleep(0.5)
                if app.like_reel():
                    likes_count += 1
                    total_actions += 1
                    if on_action_done:
                        on_action_done("like_reel", 1)
                    logger.info("✅ like_reel done - Reel liked")
                else:
                    logger.warning("❌ Failed to like Reel (may already be liked)")
            else:
                logger.warning("Failed to go to Reels tab for like_reel")
            delay()

        elif action == ActionType.VISIT_PROFILE:
            if maybe_do_nothing(0.1):
                logger.info("Skipping VISIT_PROFILE (random do-nothing)")
                delay()
                continue
            logger.info("Executing VISIT_PROFILE")
            if app.go_to_home_tab():
                time.sleep(0.5)  # Reduced wait
                if app.open_profile_from_feed():
                    total_actions += 1
                    if on_action_done:
                        on_action_done("visit_profile", 1)
                    logger.info("visit_profile done - profile opened")
                else:
                    logger.warning("Failed to open profile from feed (selectors may need update)")
            else:
                logger.warning("Failed to go to home tab for visit_profile")
            delay()

        elif action == ActionType.LIKE_POST:
            if likes_count >= plan.max_likes:
                logger.info("Skipping LIKE_POST - already at max (%s)", plan.max_likes)
                delay()
                continue
            if maybe_do_nothing(0.15):
                logger.info("Skipping LIKE_POST (random do-nothing)")
                delay()
                continue
            logger.info("Executing LIKE_POST (%s/%s)", likes_count + 1, plan.max_likes)
            if app.go_to_home_tab():
                time.sleep(0.5)  # Reduced wait
                if app.like_current_post():
                    likes_count += 1
                    total_actions += 1
                    if on_action_done:
                        on_action_done("like_post", 1)
                    logger.info("✅ like_post done - post liked")
                else:
                    logger.warning("❌ Failed to like post (may already be liked or selector issue)")
            else:
                logger.warning("Failed to go to home tab for like_post")
            delay()

        elif action == ActionType.RETURN_HOME:
            logger.info("Executing RETURN_HOME")
            if app.tap_back():
                total_actions += 1
                if on_action_done:
                    on_action_done("return_home", 1)
                logger.info("return_home done")
            else:
                logger.warning("Failed to tap back (may already be on home)")
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

        elif action == ActionType.BIO_EDIT:
            app.go_to_profile_tab()
            time.sleep(1)
            repo.set_bio_edit_done(account_id, db_path)
            total_actions += 1
            if on_action_done:
                on_action_done("bio_edit", 1)
            logger.info("bio_edit done")
            delay()

        elif action == ActionType.SEARCH_HASHTAG:
            delay()
            continue

        else:
            delay()

    session_ended_at = datetime.utcnow().isoformat() + "Z"
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
