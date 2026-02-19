"""
Flask web application for Instagram posting management.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from typing import Optional

# Ensure project root is on path and (when run as main) set cwd so data/config are found
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.posting.caption_manager import CaptionManager
from src.posting.media_queue import MediaQueue, MEDIA_QUEUE, MEDIA_PHOTOS, MEDIA_VIDEOS, MEDIA_REELS, MEDIA_CAROUSELS
from src.posting.models import MediaType, PostStatus
from src.posting.scheduler import PostScheduler

# Import CLI function to get current account (fallback if run from wrong dir)
try:
    from cli import _get_current_account
except Exception as _e:
    def _get_current_account() -> str:
        return "default"
    logging.warning("Could not import cli._get_current_account (%s); using default account.", _e)

# Global scheduler instance
_scheduler: Optional[PostScheduler] = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Use paths relative to this file so app works when run as __main__ or from cli
_WEB_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(_WEB_DIR / "templates"), static_folder=str(_WEB_DIR / "static"))
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB max file size
app.config["UPLOAD_FOLDER"] = str(MEDIA_QUEUE)

# Initialize database schema
from state.db import ensure_schema
ensure_schema()

# Initialize managers
queue_manager = MediaQueue()
caption_manager = CaptionManager()

# Allowed file extensions
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi"}


def _posting_error_message(e: Exception) -> str:
    """Return a short, user-friendly message for posting failures (e.g. Appium not running)."""
    s = str(e).lower()
    if "4723" in s or "connection refused" in s or "actively refused" in s or "connection could not be made" in s:
        return "Appium server not running. Start Appium (e.g. run 'appium') and connect your device/emulator."
    if "max retries exceeded" in s and "connection" in s:
        return "Cannot connect to Appium. Start Appium (e.g. run 'appium') and ensure device is connected."
    # Truncate long exception messages for queue display
    return str(e)[:400] if len(str(e)) > 400 else str(e)


def allowed_file(filename: str, media_type: MediaType) -> bool:
    """Check if file extension is allowed."""
    ext = Path(filename).suffix.lower()
    if media_type in [MediaType.PHOTO, MediaType.CAROUSEL]:
        return ext in ALLOWED_IMAGE_EXTENSIONS
    elif media_type in [MediaType.VIDEO, MediaType.REEL]:
        return ext in ALLOWED_VIDEO_EXTENSIONS
    return False


def save_uploaded_file(file, media_type: MediaType) -> Path:
    """Save uploaded file to appropriate directory."""
    if not allowed_file(file.filename, media_type):
        raise ValueError(f"File type not allowed: {file.filename}")
    
    # Determine target directory
    dir_map = {
        MediaType.PHOTO: MEDIA_PHOTOS,
        MediaType.VIDEO: MEDIA_VIDEOS,
        MediaType.REEL: MEDIA_REELS,
        MediaType.CAROUSEL: MEDIA_PHOTOS,  # Carousels use photos directory
    }
    target_dir = dir_map[media_type]
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    ext = Path(file.filename).suffix
    unique_name = f"{uuid.uuid4().hex}{ext}"
    target_path = target_dir / unique_name
    
    file.save(str(target_path))
    return target_path


@app.route("/")
def index():
    """Dashboard."""
    account_id = _get_current_account()
    return render_template("index.html", account_id=account_id)


@app.route("/upload")
def upload_page():
    """Upload page."""
    account_id = _get_current_account()
    return render_template("upload.html", account_id=account_id)


@app.route("/queue")
def queue_page():
    """Queue management page."""
    account_id = _get_current_account()
    return render_template("queue.html", account_id=account_id)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Upload media files."""
    try:
        account_id = _get_current_account()
        
        if "files" not in request.files:
            return jsonify({"error": "No files provided"}), 400
        
        files = request.files.getlist("files")
        if not files or files[0].filename == "":
            return jsonify({"error": "No files selected"}), 400
        
        media_type_str = request.form.get("type", "photo")
        try:
            media_type = MediaType(media_type_str)
        except ValueError:
            return jsonify({"error": f"Invalid media type: {media_type_str}"}), 400
        
        caption = request.form.get("caption", "")
        hashtags_str = request.form.get("hashtags", "")
        hashtags = [h.strip() for h in hashtags_str.split(",") if h.strip()] if hashtags_str else []
        
        scheduled_time_str = request.form.get("scheduled_time")
        scheduled_time = None
        if scheduled_time_str:
            try:
                scheduled_time = datetime.fromisoformat(scheduled_time_str.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "Invalid scheduled_time format"}), 400
        
        # Validate carousel has multiple files
        if media_type == MediaType.CAROUSEL and len(files) < 2:
            return jsonify({"error": "Carousel requires at least 2 images"}), 400
        
        # Save files
        saved_paths = []
        for file in files:
            if not allowed_file(file.filename, media_type):
                ext = Path(file.filename).suffix.lower()
                if ext in ALLOWED_VIDEO_EXTENSIONS and media_type in [MediaType.PHOTO, MediaType.CAROUSEL]:
                    return jsonify({"error": f"{file.filename} is a video. Set Post Type to Video or Reel."}), 400
                return jsonify({"error": f"File type not allowed: {file.filename}"}), 400
            saved_path = save_uploaded_file(file, media_type)
            saved_paths.append(saved_path)
        
        # Add to queue
        post_item = queue_manager.add_post(
            account_id=account_id,
            media_type=media_type,
            file_paths=saved_paths,
            caption=caption,
            hashtags=hashtags,
            scheduled_time=scheduled_time,
        )
        
        return jsonify({"success": True, "post": post_item.to_dict()}), 200
    
    except Exception as e:
        logger.error("Upload error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/queue", methods=["GET"])
def api_get_queue():
    """Get queue with optional filters."""
    account_id = request.args.get("account_id") or _get_current_account()
    status_str = request.args.get("status")
    type_str = request.args.get("type")
    
    status = PostStatus(status_str) if status_str else None
    media_type = MediaType(type_str) if type_str else None
    
    posts = queue_manager.list_queue(account_id=account_id, status=status, media_type=media_type)
    return jsonify([post.to_dict() for post in posts])


@app.route("/api/queue/<int:post_id>", methods=["PUT"])
def api_update_queue(post_id: int):
    """Update queue item."""
    try:
        data = request.get_json()
        post = queue_manager.get_post(post_id)
        
        if not post:
            return jsonify({"error": "Post not found"}), 404
        
        # Update fields
        caption = data.get("caption", post.caption)
        hashtags = data.get("hashtags", post.hashtags)
        scheduled_time_str = data.get("scheduled_time")
        
        scheduled_time = None
        if scheduled_time_str:
            scheduled_time = datetime.fromisoformat(scheduled_time_str.replace("Z", "+00:00"))
        
        # Update in database (simplified - would need update method in MediaQueue)
        # For now, delete and recreate
        queue_manager.delete_post(post_id)
        
        new_post = queue_manager.add_post(
            account_id=post.account_id,
            media_type=post.media_type,
            file_paths=post.file_paths,
            caption=caption,
            hashtags=hashtags,
            scheduled_time=scheduled_time,
        )
        
        return jsonify({"success": True, "post": new_post.to_dict()}), 200
    
    except Exception as e:
        logger.error("Update error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/queue/<int:post_id>/retry", methods=["POST"])
def api_retry_queue(post_id: int):
    """Reset a failed post to pending so it can be posted again."""
    try:
        post = queue_manager.get_post(post_id)
        if not post:
            return jsonify({"error": "Post not found"}), 404
        if post.account_id != _get_current_account():
            return jsonify({"error": "Post belongs to different account"}), 403
        if post.status != PostStatus.FAILED:
            return jsonify({"error": "Only failed posts can be retried"}), 400
        queue_manager.update_status(post_id, PostStatus.PENDING)
        return jsonify({"success": True}), 200
    except Exception as e:
        logger.error("Retry error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/queue/<int:post_id>", methods=["DELETE"])
def api_delete_queue(post_id: int):
    """Delete queue item."""
    try:
        success = queue_manager.delete_post(post_id)
        if success:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Post not found"}), 404
    except Exception as e:
        logger.error("Delete error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/post/<int:post_id>", methods=["POST"])
def api_post_now(post_id: int):
    """Post immediately."""
    try:
        post = queue_manager.get_post(post_id)
        if not post:
            return jsonify({"error": "Post not found"}), 404
        
        account_id = _get_current_account()
        if post.account_id != account_id:
            return jsonify({"error": "Post belongs to different account"}), 403
        
        # Mark as posting
        queue_manager.update_status(post_id, PostStatus.POSTING)
        
        # Import poster and driver creation
        from src.posting.poster import InstagramPoster
        from src.device.driver import create_driver
        from config.loader import get_full_config
        
        # Get config for account
        config = get_full_config(account_id)
        app_config = config.get("app", {})
        device_config = config.get("device", {})
        package = app_config.get("package", "com.instagram.android")
        adb_serial = device_config.get("adb_serial")
        
        # Check account health before posting
        from src.health.monitor import is_in_cooldown
        if is_in_cooldown(account_id):
            queue_manager.update_status(post_id, PostStatus.FAILED, error_message="Account in cooldown")
            return jsonify({"error": "Account is in cooldown. Cannot post."}), 403
        
        # Rate limit: disabled for now; re-enable later (e.g. max posts per day)
        # from datetime import date
        # today = date.today()
        # posted_today = len([p for p in queue_manager.list_queue(account_id=account_id)
        #                    if p.status == PostStatus.POSTED and p.posted_at and p.posted_at.date() == today])
        # if posted_today >= 2:
        #     queue_manager.update_status(post_id, PostStatus.FAILED, error_message="Daily post limit reached")
        #     return jsonify({"error": "Daily post limit reached (max 2 posts/day)"}), 429

        # Create driver and poster
        driver = None
        POST_TIMEOUT_SEC = 300  # 5 min max per post so we never leave "posting" stuck
        result = {"success": None, "error": None}

        def run_post():
            try:
                result["success"] = poster.post_item(post)
            except Exception as e:
                result["error"] = e

        try:
            driver = create_driver(package=package, activity=None, adb_serial=adb_serial)
            poster = InstagramPoster(driver, account_id, adb_serial=adb_serial)

            t = threading.Thread(target=run_post)
            t.daemon = True
            t.start()
            t.join(timeout=POST_TIMEOUT_SEC)

            if t.is_alive():
                logger.warning("Posting timed out after %s seconds", POST_TIMEOUT_SEC)
                queue_manager.update_status(
                    post_id, PostStatus.FAILED,
                    error_message=f"Posting timed out after {POST_TIMEOUT_SEC}s. Check device and try again."
                )
                try:
                    driver.quit()
                except Exception:
                    pass
                return jsonify({"error": "Posting timed out. Check device and try again."}), 500

            if result["error"] is not None:
                raise result["error"]

            if result["success"]:
                queue_manager.mark_posted(post_id, success=True)
                return jsonify({"success": True, "message": "Post published successfully"}), 200
            else:
                queue_manager.mark_posted(post_id, success=False, error_message="Posting failed - check device/logs")
                return jsonify({"error": "Posting failed - check logs"}), 500
        except Exception as e:
            logger.error("Posting exception: %s", e, exc_info=True)
            err_msg = _posting_error_message(e)
            queue_manager.update_status(post_id, PostStatus.FAILED, error_message=err_msg)
            return jsonify({"error": err_msg}), 500
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
    
    except Exception as e:
        logger.error("Post error: %s", e, exc_info=True)
        err_msg = _posting_error_message(e)
        queue_manager.update_status(post_id, PostStatus.FAILED, error_message=err_msg)
        return jsonify({"error": err_msg}), 500


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Get posting statistics."""
    account_id = _get_current_account()
    
    all_posts = queue_manager.list_queue(account_id=account_id)
    
    stats = {
        "total": len(all_posts),
        "pending": len([p for p in all_posts if p.status == PostStatus.PENDING]),
        "scheduled": len([p for p in all_posts if p.status == PostStatus.SCHEDULED]),
        "posted": len([p for p in all_posts if p.status == PostStatus.POSTED]),
        "failed": len([p for p in all_posts if p.status == PostStatus.FAILED]),
    }
    
    return jsonify(stats)


@app.route("/api/scheduler/status", methods=["GET"])
def api_scheduler_status():
    """Get scheduler status."""
    global _scheduler
    if _scheduler:
        return jsonify(_scheduler.get_status())
    return jsonify({"running": False, "message": "Scheduler not initialized"})


def init_scheduler():
    """Initialize and start the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return  # Already running
    account_id = _get_current_account()
    _scheduler = PostScheduler(queue_manager, account_id=account_id)
    _scheduler.start()
    logger.info("Scheduler initialized and started")


# Initialize scheduler when module loads
init_scheduler()


@app.route("/media/<path:filename>")
def serve_media(filename: str):
    """Serve media files."""
    return send_from_directory(str(MEDIA_QUEUE.parent), filename)


def create_app():
    """Create and configure Flask app."""
    # Initialize scheduler
    init_scheduler()
    return app


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
