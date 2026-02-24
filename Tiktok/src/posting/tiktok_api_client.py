"""
TikTok Content Posting API client.

Uses TikTok's official API for posting videos:
- Direct Post: POST to /v2/post/publish/video/init/ (scope: video.publish)
- Inbox upload: POST to /v2/post/publish/inbox/video/init/ (scope: video.upload)

Flow: init -> PUT video to upload_url -> poll status until PUBLISH_COMPLETE or FAILED.
See: https://developers.tiktok.com/doc/content-posting-api-get-started-upload-content
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Literal, Optional

try:
    import requests
except ImportError:
    requests = None  # type: ignore

logger = logging.getLogger(__name__)

BASE_URL = "https://open.tiktokapis.com"
UPLOAD_BASE = "https://open-upload.tiktokapis.com"

# Rate limit: 6 requests per minute per access token for init; 30/min for status
INIT_RATE_LIMIT_DELAY = 10.0   # seconds between init calls
STATUS_POLL_INTERVAL = 5.0     # seconds between status polls
STATUS_POLL_MAX_WAIT = 600     # max seconds to wait for publish (10 min)


class TikTokApiError(Exception):
    """TikTok API returned an error."""
    def __init__(self, message: str, code: Optional[str] = None, log_id: Optional[str] = None):
        self.code = code
        self.log_id = log_id
        super().__init__(message)


def _check_requests():
    if requests is None:
        raise RuntimeError("TikTok API client requires 'requests'. Install with: pip install requests")


def _parse_response(resp: requests.Response) -> Dict[str, Any]:
    _check_requests()
    data = resp.json() if resp.text else {}
    err = data.get("error", {})
    code = err.get("code", "")
    if code and code != "ok":
        raise TikTokApiError(
            err.get("message", "Unknown API error"),
            code=code,
            log_id=err.get("log_id"),
        )
    return data


def init_direct_post(
    access_token: str,
    video_path: Path,
    title: str = "",
    privacy_level: str = "SELF_ONLY",
    disable_duet: bool = False,
    disable_stitch: bool = False,
    disable_comment: bool = False,
    chunk_size: int = 10 * 1024 * 1024,
) -> tuple[str, str]:
    """
    Initialize a Direct Post (video goes live on profile).
    Returns (publish_id, upload_url).
    Unaudited apps can only use SELF_ONLY (private).
    """
    _check_requests()
    size = video_path.stat().st_size
    total_chunks = (size + chunk_size - 1) // chunk_size
    payload = {
        "post_info": {
            "title": title,
            "privacy_level": privacy_level,
            "disable_duet": disable_duet,
            "disable_stitch": disable_stitch,
            "disable_comment": disable_comment,
            "brand_content_toggle": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks,
        },
    }
    url = f"{BASE_URL}/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    r = requests.post(url, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    data = _parse_response(r)
    info = data.get("data", {})
    publish_id = info.get("publish_id")
    upload_url = info.get("upload_url")
    if not publish_id or not upload_url:
        raise TikTokApiError("Init response missing publish_id or upload_url")
    return publish_id, upload_url


def init_inbox_upload(
    access_token: str,
    video_path: Path,
    chunk_size: int = 10 * 1024 * 1024,
) -> tuple[str, str]:
    """
    Initialize an Inbox upload (video goes to creator's inbox as draft).
    Returns (publish_id, upload_url).
    """
    _check_requests()
    size = video_path.stat().st_size
    total_chunks = (size + chunk_size - 1) // chunk_size
    payload = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks,
        },
    }
    url = f"{BASE_URL}/v2/post/publish/inbox/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    r = requests.post(url, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    data = _parse_response(r)
    info = data.get("data", {})
    publish_id = info.get("publish_id")
    upload_url = info.get("upload_url")
    if not publish_id or not upload_url:
        raise TikTokApiError("Init response missing publish_id or upload_url")
    return publish_id, upload_url


def upload_video_file(upload_url: str, video_path: Path) -> None:
    """PUT video file to TikTok upload_url. Single-chunk upload."""
    _check_requests()
    size = video_path.stat().st_size
    headers = {
        "Content-Type": "video/mp4",
        "Content-Length": str(size),
        "Content-Range": f"bytes 0-{size - 1}/{size}",
    }
    with open(video_path, "rb") as f:
        r = requests.put(upload_url, data=f, headers=headers, timeout=300)
    r.raise_for_status()


def get_publish_status(access_token: str, publish_id: str) -> Dict[str, Any]:
    """Fetch status for a publish_id. Returns data dict with status, fail_reason, etc."""
    _check_requests()
    url = f"{BASE_URL}/v2/post/publish/status/fetch/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    r = requests.post(url, json={"publish_id": publish_id}, headers=headers, timeout=30)
    r.raise_for_status()
    data = _parse_response(r)
    return data.get("data", {})


def wait_for_publish(
    access_token: str,
    publish_id: str,
    poll_interval: float = STATUS_POLL_INTERVAL,
    max_wait: float = STATUS_POLL_MAX_WAIT,
) -> Literal["PUBLISH_COMPLETE", "FAILED"]:
    """
    Poll status until PUBLISH_COMPLETE or FAILED.
    Returns final status; raises TikTokApiError on failure with fail_reason.
    """
    start = time.monotonic()
    while (time.monotonic() - start) < max_wait:
        info = get_publish_status(access_token, publish_id)
        status = info.get("status", "")
        if status == "PUBLISH_COMPLETE":
            return "PUBLISH_COMPLETE"
        if status == "FAILED":
            reason = info.get("fail_reason", "unknown")
            raise TikTokApiError(f"Publish failed: {reason}", code=reason)
        if status in ("PROCESSING_UPLOAD", "PROCESSING_DOWNLOAD", "SEND_TO_USER_INBOX"):
            logger.debug("Publish status: %s", status)
        time.sleep(poll_interval)
    raise TikTokApiError("Publish timed out waiting for completion")
