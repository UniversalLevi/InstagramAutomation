"""
Media Queue: Manage TikTok posts in queue; single video per post.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from state import db as db_module
from state.db import DEFAULT_DB_PATH

from .models import MediaType, PostItem, PostStatus

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MEDIA_ROOT = PROJECT_ROOT / "media"
MEDIA_QUEUE = MEDIA_ROOT / "queue"
MEDIA_POSTED = MEDIA_ROOT / "posted"
MEDIA_FAILED = MEDIA_ROOT / "failed"
MEDIA_VIDEOS = MEDIA_QUEUE / "videos"


def _ensure_media_directories():
    for dir_path in [MEDIA_QUEUE, MEDIA_POSTED, MEDIA_FAILED, MEDIA_VIDEOS]:
        dir_path.mkdir(parents=True, exist_ok=True)


class MediaQueue:
    """Manages post queue using SQLite. Video-only."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        _ensure_media_directories()

    def add_post(
        self,
        account_id: str,
        media_type: MediaType,
        file_paths: List[Path],
        caption: str = "",
        hashtags: Optional[List[str]] = None,
        scheduled_time: Optional[datetime] = None,
        db_path: Optional[Path] = None,
    ) -> PostItem:
        hashtags = hashtags or []
        for fp in file_paths:
            if not fp.exists():
                raise FileNotFoundError(f"Media file not found: {fp}")
        status = PostStatus.SCHEDULED if scheduled_time else PostStatus.PENDING
        file_paths_json = json.dumps([str(p) for p in file_paths])
        hashtags_json = json.dumps(hashtags)
        scheduled_time_str = scheduled_time.isoformat() if scheduled_time else None
        created_at = datetime.utcnow().isoformat() + "Z"
        db_path = db_path or self.db_path
        with db_module.cursor(db_path) as cur:
            cur.execute(
                """
                INSERT INTO post_queue
                (account_id, media_type, file_paths, caption, hashtags, scheduled_time, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (account_id, media_type.value, file_paths_json, caption, hashtags_json, scheduled_time_str, status.value, created_at),
            )
            post_id = cur.lastrowid
        logger.info("Added post %s to queue: %s (%s files)", post_id, media_type.value, len(file_paths))
        return PostItem(
            id=post_id,
            account_id=account_id,
            media_type=media_type,
            file_paths=file_paths,
            caption=caption,
            hashtags=hashtags,
            scheduled_time=scheduled_time,
            status=status,
            created_at=datetime.fromisoformat(created_at.replace("Z", "+00:00")),
        )

    def get_next_post(self, account_id: Optional[str] = None, db_path: Optional[Path] = None) -> Optional[PostItem]:
        db_path = db_path or self.db_path
        now = datetime.utcnow().isoformat() + "Z"
        with db_module.cursor(db_path) as cur:
            if account_id:
                cur.execute(
                    """
                    SELECT * FROM post_queue
                    WHERE account_id = ? AND status IN ('pending', 'scheduled')
                    AND (scheduled_time IS NULL OR scheduled_time <= ?)
                    ORDER BY scheduled_time ASC NULLS LAST, created_at ASC
                    LIMIT 1
                    """,
                    (account_id, now),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM post_queue
                    WHERE status IN ('pending', 'scheduled')
                    AND (scheduled_time IS NULL OR scheduled_time <= ?)
                    ORDER BY scheduled_time ASC NULLS LAST, created_at ASC
                    LIMIT 1
                    """,
                    (now,),
                )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_post_item(row)

    def update_status(
        self,
        post_id: int,
        status: PostStatus,
        error_message: Optional[str] = None,
        db_path: Optional[Path] = None,
    ):
        db_path = db_path or self.db_path
        now = datetime.utcnow().isoformat() + "Z"
        with db_module.cursor(db_path) as cur:
            if status == PostStatus.POSTED:
                cur.execute(
                    "UPDATE post_queue SET status = ?, posted_at = ?, error_message = NULL WHERE id = ?",
                    (status.value, now, post_id),
                )
            elif status == PostStatus.FAILED:
                cur.execute(
                    "UPDATE post_queue SET status = ?, error_message = ? WHERE id = ?",
                    (status.value, error_message, post_id),
                )
            elif status == PostStatus.POSTING:
                cur.execute(
                    "UPDATE post_queue SET status = ? WHERE id = ?",
                    (status.value, post_id),
                )
            else:
                cur.execute(
                    "UPDATE post_queue SET status = ?, error_message = NULL WHERE id = ?",
                    (status.value, post_id),
                )
        logger.info("Updated post %s status to %s", post_id, status.value)

    def mark_posted(self, post_id: int, success: bool = True, error_message: Optional[str] = None, db_path: Optional[Path] = None):
        db_path = db_path or self.db_path
        post = self.get_post(post_id, db_path=db_path)
        if not post:
            return
        status = PostStatus.POSTED if success else PostStatus.FAILED
        self.update_status(post_id, status, error_message, db_path)
        target_dir = MEDIA_POSTED if success else MEDIA_FAILED
        target_dir.mkdir(parents=True, exist_ok=True)
        for fp in post.file_paths:
            try:
                if fp.exists():
                    shutil.move(str(fp), str(target_dir / fp.name))
                    logger.info("Moved %s to %s", fp.name, target_dir.name)
            except Exception as e:
                logger.warning("Failed to move file %s: %s", fp.name, e)

    def get_post(self, post_id: int, db_path: Optional[Path] = None) -> Optional[PostItem]:
        db_path = db_path or self.db_path
        with db_module.cursor(db_path) as cur:
            cur.execute("SELECT * FROM post_queue WHERE id = ?", (post_id,))
            row = cur.fetchone()
            return self._row_to_post_item(row) if row else None

    def list_queue(
        self,
        account_id: Optional[str] = None,
        status: Optional[PostStatus] = None,
        media_type: Optional[MediaType] = None,
        db_path: Optional[Path] = None,
    ) -> List[PostItem]:
        db_path = db_path or self.db_path
        conditions = []
        params = []
        if account_id:
            conditions.append("account_id = ?")
            params.append(account_id)
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if media_type:
            conditions.append("media_type = ?")
            params.append(media_type.value)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        with db_module.cursor(db_path) as cur:
            cur.execute(
                f"SELECT * FROM post_queue WHERE {where_clause} ORDER BY created_at DESC, id DESC",
                params,
            )
            rows = cur.fetchall()
            return [self._row_to_post_item(row) for row in rows]

    def delete_post(self, post_id: int, db_path: Optional[Path] = None) -> bool:
        db_path = db_path or self.db_path
        post = self.get_post(post_id, db_path=db_path)
        with db_module.cursor(db_path) as cur:
            cur.execute("DELETE FROM post_queue WHERE id = ?", (post_id,))
            deleted = cur.rowcount > 0
        if deleted and post:
            for fp in post.file_paths:
                try:
                    if fp.exists():
                        fp.unlink()
                        logger.info("Deleted file %s", fp.name)
                except Exception as e:
                    logger.warning("Failed to delete file %s: %s", fp.name, e)
        return deleted

    def _row_to_post_item(self, row) -> PostItem:
        file_paths = json.loads(row["file_paths"])
        hashtags = json.loads(row["hashtags"]) if row["hashtags"] else []
        scheduled_time = None
        if row["scheduled_time"]:
            scheduled_time = datetime.fromisoformat(row["scheduled_time"])
        created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")) if row["created_at"] else None
        posted_at = datetime.fromisoformat(row["posted_at"].replace("Z", "+00:00")) if row["posted_at"] else None
        return PostItem(
            id=row["id"],
            account_id=row["account_id"],
            media_type=MediaType(row["media_type"]),
            file_paths=[Path(p) for p in file_paths],
            caption=row["caption"] or "",
            hashtags=hashtags,
            scheduled_time=scheduled_time,
            status=PostStatus(row["status"]),
            created_at=created_at,
            posted_at=posted_at,
            error_message=row["error_message"],
        )
