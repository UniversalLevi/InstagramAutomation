"""
TikTok posting via Content Posting API (no device/Appium).

Uses TikTok's official API: init -> upload file -> poll status.
Same interface as poster.TikTokPoster: post_item(post_item) -> bool.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.posting.models import MediaType, PostItem
from src.posting.tiktok_api_client import (
    TikTokApiError,
    init_direct_post,
    init_inbox_upload,
    upload_video_file,
    wait_for_publish,
)

logger = logging.getLogger(__name__)


class TikTokApiPoster:
    """Handles posting video to TikTok via Content Posting API."""

    def __init__(self, account_id: str):
        self.account_id = account_id

    def _get_api_config(self) -> dict:
        from config.loader import get_full_config
        config = get_full_config(self.account_id)
        api_config = config.get("tiktok_api") or {}
        if not api_config or not api_config.get("access_token"):
            raise ValueError(
                "TikTok API not configured for this account. "
                "Add tiktok_api.access_token (and client_key, client_secret) to account config."
            )
        return api_config

    def _build_title(self, caption: str, hashtags: List[str]) -> str:
        parts = []
        if caption:
            parts.append(caption)
        if hashtags:
            parts.append(" ".join(hashtags))
        return "\n\n".join(parts).strip() or ""

    def post_item(self, post_item: PostItem) -> bool:
        if post_item.media_type != MediaType.VIDEO:
            logger.error("TikTok API supports video only")
            return False
        if not post_item.file_paths:
            logger.error("No file path in post item")
            return False
        video_path = Path(post_item.file_paths[0])
        if not video_path.exists():
            logger.error("Video file not found: %s", video_path)
            return False

        api_config = self._get_api_config()
        access_token = api_config["access_token"]
        post_mode = api_config.get("post_mode", "direct")
        privacy_level = api_config.get("privacy_level", "SELF_ONLY")
        title = self._build_title(post_item.caption, post_item.hashtags or [])

        try:
            if post_mode == "inbox":
                publish_id, upload_url = init_inbox_upload(access_token, video_path)
            else:
                publish_id, upload_url = init_direct_post(
                    access_token,
                    video_path,
                    title=title,
                    privacy_level=privacy_level,
                )
            logger.info("Init OK, publish_id=%s; uploading file", publish_id)
            upload_video_file(upload_url, video_path)
            logger.info("Upload OK; waiting for publish status")
            wait_for_publish(access_token, publish_id)
            logger.info("Publish complete")
            return True
        except TikTokApiError as e:
            logger.error("TikTok API error: %s (code=%s)", e, e.code)
            return False
        except Exception as e:
            logger.error("Post failed: %s", e, exc_info=True)
            return False
