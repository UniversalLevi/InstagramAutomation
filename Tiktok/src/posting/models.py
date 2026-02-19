"""
Data models for TikTok posting. Video-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional


class MediaType(str, Enum):
    VIDEO = "video"


class PostStatus(str, Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    POSTING = "posting"
    POSTED = "posted"
    FAILED = "failed"


@dataclass
class PostItem:
    """Represents a post in the queue."""
    id: Optional[int] = None
    account_id: str = ""
    media_type: MediaType = MediaType.VIDEO
    file_paths: List[Path] = field(default_factory=list)
    caption: str = ""
    hashtags: List[str] = field(default_factory=list)
    scheduled_time: Optional[datetime] = None
    status: PostStatus = PostStatus.PENDING
    created_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "media_type": self.media_type.value,
            "file_paths": [str(p) for p in self.file_paths],
            "caption": self.caption,
            "hashtags": self.hashtags,
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PostItem:
        return cls(
            id=data.get("id"),
            account_id=data.get("account_id", ""),
            media_type=MediaType(data.get("media_type", "video")),
            file_paths=[Path(p) for p in data.get("file_paths", [])],
            caption=data.get("caption", ""),
            hashtags=data.get("hashtags", []),
            scheduled_time=datetime.fromisoformat(data["scheduled_time"]) if data.get("scheduled_time") else None,
            status=PostStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            posted_at=datetime.fromisoformat(data["posted_at"]) if data.get("posted_at") else None,
            error_message=data.get("error_message"),
        )
