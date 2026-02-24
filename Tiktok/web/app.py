"""
Flask web application for TikTok posting management.
"""
from __future__ import annotations

import logging
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.posting.caption_manager import CaptionManager
from src.posting.media_queue import MediaQueue, MEDIA_QUEUE, MEDIA_VIDEOS
from src.posting.models import MediaType, PostStatus
from src.posting.scheduler import PostScheduler, _posting_lock

try:
    from cli import _get_current_account
except Exception as _e:
    def _get_current_account() -> str:
        return "default"
    logging.warning("Could not import cli._get_current_account (%s); using default account.", _e)

_scheduler: Optional[PostScheduler] = None
_cleanup_interval_sec = 120  # delete stuck/failed debug files every 2 minutes
_cleanup_thread_started = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Glob patterns for debug files created when posting gets stuck or fails (relative to PROJECT_ROOT)
_DEBUG_FILE_PATTERNS = [
    "post_stuck_*.txt",
    "post_stuck_*.png",
    "post_failed_*.png",
    "post_debug_screen.txt",
    "post_debug_screen.png",
]


def _cleanup_stuck_debug_files() -> None:
    """Delete captured stuck/failed screenshots and screen dumps from PROJECT_ROOT."""
    try:
        deleted = 0
        for pattern in _DEBUG_FILE_PATTERNS:
            for path in PROJECT_ROOT.glob(pattern):
                try:
                    path.unlink()
                    deleted += 1
                    logger.debug("Cleaned up debug file: %s", path.name)
                except OSError as e:
                    logger.debug("Could not delete %s: %s", path, e)
        if deleted:
            logger.info("Cleanup: removed %d stuck/failed debug file(s)", deleted)
    except Exception as e:
        logger.warning("Cleanup of debug files failed: %s", e)


def _cleanup_loop() -> None:
    """Background loop: run cleanup every 2 minutes."""
    import time
    while True:
        time.sleep(_cleanup_interval_sec)
        _cleanup_stuck_debug_files()

_WEB_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(_WEB_DIR / "templates"), static_folder=str(_WEB_DIR / "static"))
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(MEDIA_QUEUE)

from state.db import ensure_schema
ensure_schema()

queue_manager = MediaQueue()
caption_manager = CaptionManager()

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi"}


def _posting_error_message(e: Exception) -> str:
    s = str(e).lower()
    if "4723" in s or "connection refused" in s or "actively refused" in s or "connection could not be made" in s:
        return "Appium server not running. Start Appium and connect your device/emulator."
    if "max retries exceeded" in s and "connection" in s:
        return "Cannot connect to Appium. Start Appium and ensure device is connected."
    return str(e)[:400] if len(str(e)) > 400 else str(e)


def allowed_file(filename: str, media_type: MediaType) -> bool:
    ext = Path(filename).suffix.lower()
    return media_type == MediaType.VIDEO and ext in ALLOWED_VIDEO_EXTENSIONS


def save_uploaded_file(file, media_type: MediaType) -> Path:
    if not allowed_file(file.filename, media_type):
        raise ValueError(f"File type not allowed: {file.filename}")
    MEDIA_VIDEOS.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix
    unique_name = f"{uuid.uuid4().hex}{ext}"
    target_path = MEDIA_VIDEOS / unique_name
    file.save(str(target_path))
    return target_path


# TikTok OAuth: use localhost so you don't need ngrok. Add this exact URI in Developer Portal:
# http://127.0.0.1:5001/oauth/callback
_TIKTOK_OAUTH = {
    "client_key": "sbaw4oy89sm5o0iids",
    "redirect_uri": "http://127.0.0.1:5001/oauth/callback",
    "scope": "video.publish,video.upload",
}
_TIKTOK_AUTH_URL = (
    "https://www.tiktok.com/auth/authorize/"
    f"?client_key={_TIKTOK_OAUTH['client_key']}"
    f"&scope={_TIKTOK_OAUTH['scope']}"
    f"&response_type=code"
    f"&redirect_uri={_TIKTOK_OAUTH['redirect_uri']}"
    "&state=random123"
)
_TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


@app.route("/oauth/authorize")
def oauth_authorize():
    """Redirect to TikTok auth with the correct URL (no copy-paste errors)."""
    return redirect(_TIKTOK_AUTH_URL)


@app.route("/oauth/callback")
def oauth_callback():
    """TikTok redirects here with ?code=...; we exchange it for a token and save to config."""
    import requests
    from config.loader import get_account_config, save_account_config

    account_id = _get_current_account()
    code = request.args.get("code")
    error_param = request.args.get("error")

    if error_param:
        return render_template(
            "oauth_result.html",
            account_id=account_id,
            success=False,
            message=f"TikTok returned an error: {error_param}. Make sure you're logged in with a Sandbox Target User account.",
        )
    if not code:
        return render_template(
            "oauth_result.html",
            account_id=account_id,
            success=False,
            message="No authorization code received. Try again from the Dashboard.",
        )

    # Load account config to get client_secret
    acc = get_account_config(account_id)
    tiktok_api = acc.get("tiktok_api") or {}
    client_secret = tiktok_api.get("client_secret") or acc.get("client_secret")
    if not client_secret:
        return render_template(
            "oauth_result.html",
            account_id=account_id,
            success=False,
            message="Add client_secret to config. In config/accounts/default.yaml add: tiktok_api: client_key: sbaw4oy89sm5o0iids  client_secret: YOUR_CLIENT_SECRET",
        )

    # Exchange code for token
    try:
        resp = requests.post(
            _TIKTOK_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key": _TIKTOK_OAUTH["client_key"],
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": _TIKTOK_OAUTH["redirect_uri"],
            },
            timeout=15,
        )
        data = resp.json()
    except Exception as e:
        logger.exception("Token exchange request failed")
        return render_template(
            "oauth_result.html",
            account_id=account_id,
            success=False,
            message=f"Request failed: {e}",
        )

    if "access_token" not in data:
        err = data.get("error", data.get("message", str(data)))
        return render_template(
            "oauth_result.html",
            account_id=account_id,
            success=False,
            message=f"TikTok token error: {err}. Check that redirect_uri in Developer Portal is exactly: {_TIKTOK_OAUTH['redirect_uri']}",
        )

    # Save tokens to account config (merge with existing tiktok_api)
    updates = {
        "tiktok_api": {
            **tiktok_api,
            "client_key": _TIKTOK_OAUTH["client_key"],
            "client_secret": client_secret,
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token") or tiktok_api.get("refresh_token"),
            "open_id": data.get("open_id") or tiktok_api.get("open_id"),
            "post_mode": tiktok_api.get("post_mode", "direct"),
            "privacy_level": tiktok_api.get("privacy_level", "SELF_ONLY"),
        }
    }
    try:
        save_account_config(account_id, updates)
        logger.info("TikTok access token saved for account %s", account_id)
    except Exception as e:
        logger.exception("Failed to save config")
        return render_template(
            "oauth_result.html",
            account_id=account_id,
            success=False,
            message=f"Token received but saving config failed: {e}",
        )

    return render_template(
        "oauth_result.html",
        account_id=account_id,
        success=True,
        message="Access token saved. You can use API posting now.",
    )


@app.route("/")
def index():
    account_id = _get_current_account()
    # If TikTok redirected here with ?code=... (old ngrok-style), send to callback
    code = request.args.get("code")
    if code and request.path == "/":
        return redirect(url_for("oauth_callback", code=code, **request.args))
    return render_template("index.html", account_id=account_id)


@app.route("/upload")
def upload_page():
    account_id = _get_current_account()
    return render_template("upload.html", account_id=account_id)


@app.route("/queue")
def queue_page():
    account_id = _get_current_account()
    return render_template("queue.html", account_id=account_id)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    try:
        account_id = _get_current_account()
        if "files" not in request.files:
            return jsonify({"error": "No files provided"}), 400
        files = request.files.getlist("files")
        if not files or files[0].filename == "":
            return jsonify({"error": "No files selected"}), 400
        media_type_str = request.form.get("type", "video")
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

        saved_paths = []
        for file in files:
            if not allowed_file(file.filename, media_type):
                return jsonify({"error": f"File type not allowed: {file.filename}. Use video (MP4, MOV, AVI)."}), 400
            saved_path = save_uploaded_file(file, media_type)
            saved_paths.append(saved_path)

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
    account_id = request.args.get("account_id") or _get_current_account()
    status_str = request.args.get("status")
    type_str = request.args.get("type")
    status = PostStatus(status_str) if status_str else None
    media_type = MediaType(type_str) if type_str else None
    posts = queue_manager.list_queue(account_id=account_id, status=status, media_type=media_type)
    return jsonify([post.to_dict() for post in posts])


@app.route("/api/queue/<int:post_id>", methods=["PUT"])
def api_update_queue(post_id: int):
    try:
        data = request.get_json()
        post = queue_manager.get_post(post_id)
        if not post:
            return jsonify({"error": "Post not found"}), 404
        caption = data.get("caption", post.caption)
        hashtags = data.get("hashtags", post.hashtags)
        scheduled_time_str = data.get("scheduled_time")
        scheduled_time = None
        if scheduled_time_str:
            scheduled_time = datetime.fromisoformat(scheduled_time_str.replace("Z", "+00:00"))
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
    try:
        success = queue_manager.delete_post(post_id)
        if success:
            return jsonify({"success": True}), 200
        return jsonify({"error": "Post not found"}), 404
    except Exception as e:
        logger.error("Delete error: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/post/<int:post_id>", methods=["POST"])
def api_post_now(post_id: int):
    try:
        post = queue_manager.get_post(post_id)
        if not post:
            return jsonify({"error": "Post not found"}), 404
        account_id = _get_current_account()
        if post.account_id != account_id:
            return jsonify({"error": "Post belongs to different account"}), 403
        queue_manager.update_status(post_id, PostStatus.POSTING)

        from src.posting.poster import TikTokPoster
        from src.device.driver import create_driver
        from config.loader import get_full_config
        from src.health.monitor import is_in_cooldown

        if is_in_cooldown(account_id):
            queue_manager.update_status(post_id, PostStatus.FAILED, error_message="Account in cooldown")
            return jsonify({"error": "Account is in cooldown. Cannot post."}), 403

        if not _posting_lock.acquire(blocking=False):
            queue_manager.update_status(post_id, PostStatus.PENDING)
            return jsonify({"error": "Another post is in progress. Try again shortly."}), 429

        config = get_full_config(account_id)
        posting_config = config.get("posting", {}) or {}
        method = posting_config.get("method", "appium")

        if method == "api":
            try:
                from src.posting.api_poster import TikTokApiPoster
                poster = TikTokApiPoster(account_id)
                success = poster.post_item(post)
                _posting_lock.release()
                if success:
                    queue_manager.mark_posted(post_id, success=True)
                    return jsonify({"success": True, "message": "Post published successfully"}), 200
                queue_manager.mark_posted(post_id, success=False, error_message="TikTok API posting failed")
                return jsonify({"error": "Posting failed - check logs"}), 500
            except Exception as e:
                _posting_lock.release()
                err_msg = str(e)[:400]
                queue_manager.update_status(post_id, PostStatus.FAILED, error_message=err_msg)
                return jsonify({"error": err_msg}), 500

        POST_TIMEOUT_SEC = 300
        result = {"success": None, "error": None}
        driver_holder = {}  # shared ref so we can quit driver on timeout

        def run_post():
            dr = None
            try:
                from src.device.driver import create_driver
                from src.posting.poster import TikTokPoster
                app_config = config.get("app", {})
                device_config = config.get("device", {})
                package = app_config.get("package", "com.zhiliaoapp.musically")
                adb_serial = device_config.get("adb_serial")
                dr = create_driver(package=package, adb_serial=adb_serial)
                driver_holder["driver"] = dr
                poster = TikTokPoster(dr, account_id, adb_serial)
                result["success"] = poster.post_item(post)
            except Exception as e:
                result["error"] = e
            finally:
                if dr is not None:
                    try:
                        dr.quit()
                    except Exception:
                        pass
                    driver_holder.pop("driver", None)

        try:
            t = threading.Thread(target=run_post, daemon=True)
            t.start()
            t.join(timeout=POST_TIMEOUT_SEC)

            if t.is_alive():
                logger.warning("Posting timed out after %s seconds", POST_TIMEOUT_SEC)
                queue_manager.update_status(
                    post_id, PostStatus.FAILED,
                    error_message=f"Posting timed out after {POST_TIMEOUT_SEC}s.",
                )
                dr = driver_holder.pop("driver", None)
                if dr is not None:
                    try:
                        dr.quit()
                    except Exception:
                        pass
                _posting_lock.release()
                return jsonify({"error": "Posting timed out. Check device and try again."}), 500

            _posting_lock.release()

            if result["error"] is not None:
                raise result["error"]
            if result["success"]:
                queue_manager.mark_posted(post_id, success=True)
                return jsonify({"success": True, "message": "Post published successfully"}), 200
            queue_manager.mark_posted(post_id, success=False, error_message="Posting failed - check device/logs")
            return jsonify({"error": "Posting failed - check logs"}), 500
        except Exception as e:
            _posting_lock.release()
            logger.error("Posting exception: %s", e, exc_info=True)
            err_msg = _posting_error_message(e)
            queue_manager.update_status(post_id, PostStatus.FAILED, error_message=err_msg)
            return jsonify({"error": err_msg}), 500
    except Exception as e:
        logger.error("Post error: %s", e, exc_info=True)
        err_msg = _posting_error_message(e)
        queue_manager.update_status(post_id, PostStatus.FAILED, error_message=err_msg)
        return jsonify({"error": err_msg}), 500


@app.route("/api/stats", methods=["GET"])
def api_stats():
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
    global _scheduler
    if _scheduler:
        return jsonify(_scheduler.get_status())
    return jsonify({"running": False, "message": "Scheduler not initialized"})


def init_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        return
    account_id = _get_current_account()
    _scheduler = PostScheduler(queue_manager, account_id=account_id)
    _scheduler.start()
    logger.info("Scheduler initialized and started")


def init_cleanup_thread():
    """Start background thread that deletes stuck/failed debug files every 2 minutes."""
    global _cleanup_thread_started
    if _cleanup_thread_started:
        return
    _cleanup_thread_started = True
    t = threading.Thread(target=_cleanup_loop, daemon=True)
    t.start()
    logger.info("Debug file cleanup started (every %s seconds)", _cleanup_interval_sec)


init_scheduler()
init_cleanup_thread()


@app.route("/media/<path:filename>")
def serve_media(filename: str):
    return send_from_directory(str(MEDIA_QUEUE.parent), filename)


def create_app():
    init_scheduler()
    init_cleanup_thread()
    return app


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
