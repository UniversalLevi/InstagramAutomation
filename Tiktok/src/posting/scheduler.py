"""
Background scheduler for scheduled TikTok posts. Wires _trigger_posting to driver + poster.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.posting.media_queue import MediaQueue
from src.posting.models import PostStatus

logger = logging.getLogger(__name__)

# Lock so only one post runs at a time (scheduler or web)
_posting_lock = threading.Lock()


class PostScheduler:
    """Background scheduler that checks for scheduled posts and triggers posting."""

    def __init__(self, queue_manager: MediaQueue, account_id: Optional[str] = None):
        self.queue_manager = queue_manager
        self.account_id = account_id
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.check_interval = 60

    def start(self):
        if self.running:
            logger.warning("Scheduler already running")
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("Post scheduler started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Post scheduler stopped")

    def _run(self):
        while self.running:
            try:
                self._check_and_post()
            except Exception as e:
                logger.error("Scheduler error: %s", e, exc_info=True)
            for _ in range(self.check_interval):
                if not self.running:
                    break
                time.sleep(1)

    def _check_and_post(self):
        try:
            post = self.queue_manager.get_next_post(account_id=self.account_id)
            if post and post.status in [PostStatus.PENDING, PostStatus.SCHEDULED]:
                now = datetime.utcnow()
                if not post.scheduled_time or post.scheduled_time <= now:
                    logger.info("Found post ready to publish: %s (type: %s)", post.id, post.media_type.value)
                    self._trigger_posting(post.id)
        except Exception as e:
            logger.error("Error checking scheduled posts: %s", e)

    def _trigger_posting(self, post_id: int):
        """Create driver, run TikTokPoster.post_item, then mark_posted."""
        if not _posting_lock.acquire(blocking=False):
            logger.warning("Posting already in progress, skipping post %s", post_id)
            return
        try:
            post = self.queue_manager.get_post(post_id)
            if not post:
                logger.error("Post %s not found", post_id)
                return
            account_id = post.account_id
            if self.account_id and account_id != self.account_id:
                return

            from config.loader import get_full_config
            from src.device.driver import create_driver
            from src.posting.poster import TikTokPoster
            from src.health.monitor import is_in_cooldown

            if is_in_cooldown(account_id):
                self.queue_manager.update_status(post_id, PostStatus.FAILED, error_message="Account in cooldown")
                return

            self.queue_manager.update_status(post_id, PostStatus.POSTING)
            config = get_full_config(account_id)
            app_config = config.get("app", {})
            device_config = config.get("device", {})
            package = app_config.get("package", "com.zhiliaoapp.musically")
            adb_serial = device_config.get("adb_serial")

            driver = None
            try:
                driver = create_driver(package=package, adb_serial=adb_serial)
                poster = TikTokPoster(driver, account_id, adb_serial)
                success = poster.post_item(post)
                self.queue_manager.mark_posted(post_id, success=success)
            except Exception as e:
                logger.error("Post %s failed: %s", post_id, e, exc_info=True)
                self.queue_manager.mark_posted(post_id, success=False, error_message=str(e)[:500])
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
        finally:
            _posting_lock.release()

    def get_status(self) -> dict:
        return {
            "running": self.running,
            "account_id": self.account_id,
            "check_interval": self.check_interval,
        }
