"""
Background scheduler service for scheduled posts.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Optional

from src.posting.media_queue import MediaQueue
from src.posting.models import PostStatus

logger = logging.getLogger(__name__)


class PostScheduler:
    """Background scheduler that checks for scheduled posts and triggers posting."""
    
    def __init__(self, queue_manager: MediaQueue, account_id: Optional[str] = None):
        self.queue_manager = queue_manager
        self.account_id = account_id
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.check_interval = 60  # Check every minute
    
    def start(self):
        """Start the scheduler in a background thread."""
        if self.running:
            logger.warning("Scheduler already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("Post scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Post scheduler stopped")
    
    def _run(self):
        """Main scheduler loop."""
        while self.running:
            try:
                self._check_and_post()
            except Exception as e:
                logger.error("Scheduler error: %s", e, exc_info=True)
            
            # Sleep for check interval
            for _ in range(self.check_interval):
                if not self.running:
                    break
                time.sleep(1)
    
    def _check_and_post(self):
        """Check for scheduled posts ready to post and trigger posting."""
        try:
            # Get next post ready to post
            post = self.queue_manager.get_next_post(account_id=self.account_id)
            
            if post and post.status in [PostStatus.PENDING, PostStatus.SCHEDULED]:
                # Check if scheduled time has arrived
                now = datetime.utcnow()
                if not post.scheduled_time or post.scheduled_time <= now:
                    logger.info("Found post ready to publish: %s (type: %s)", post.id, post.media_type.value)
                    # Trigger posting (will be handled by web API or separate posting service)
                    # For now, just log - actual posting will be triggered via API
                    self._trigger_posting(post.id)
        except Exception as e:
            logger.error("Error checking scheduled posts: %s", e)
    
    def _trigger_posting(self, post_id: int):
        """Trigger posting for a post. This will call the posting API."""
        # In a full implementation, this would call the posting service
        # For now, we'll rely on the web API endpoint being called
        # The scheduler just identifies posts ready to post
        logger.info("Post %s is ready to be posted (trigger via API)", post_id)
    
    def get_status(self) -> dict:
        """Get scheduler status."""
        return {
            "running": self.running,
            "account_id": self.account_id,
            "check_interval": self.check_interval,
        }
