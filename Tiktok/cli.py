#!/usr/bin/env python3
"""
TikTok Warm-Up CLI. Run from tiktok project root.
Usage:
  python cli.py
  python cli.py start [account_id] [--force]
  python cli.py status [account_id]
  python cli.py stop
  python cli.py list
  python cli.py select <account_id>
Manual login only: log in to TikTok on the device once, then run start.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.loader import get_full_config, list_account_configs
from state import repository as repo
from state.db import DEFAULT_DB_PATH, ensure_schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_stop_requested = False
_run_thread = None

CURRENT_ACCOUNT_FILE = PROJECT_ROOT / "data" / "current_account.txt"


def _get_current_account() -> str:
    if CURRENT_ACCOUNT_FILE.exists():
        try:
            return CURRENT_ACCOUNT_FILE.read_text(encoding="utf-8").strip() or "default"
        except Exception:
            pass
    return "default"


def _set_current_account(account_id: str) -> None:
    CURRENT_ACCOUNT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CURRENT_ACCOUNT_FILE.write_text(account_id, encoding="utf-8")


def _cmd_status(account_id: str) -> int:
    ensure_schema()
    acc = repo.get_account(account_id)
    if not acc:
        print(f"Account '{account_id}' not found in state. Run start first (after adding config).")
        return 1
    first = acc.get("first_run_date")
    last = acc.get("last_run_date")
    total, likes = repo.get_today_totals(account_id)
    print(f"Account: {account_id}")
    print(f"  First run: {first}")
    print(f"  Last run:  {last}")
    print(f"  Today: total_actions={total}, likes={likes}")
    return 0


def _cmd_start(account_id: str, force: bool = False) -> int:
    global _stop_requested, _run_thread
    _stop_requested = False
    ensure_schema()

    config = get_full_config(account_id)
    limits = config.get("limits", {})
    one_session_per_day = limits.get("one_session_per_day", True)
    today = __import__("datetime").date.today()

    first_run_date = repo.get_first_run_date(account_id)
    if not first_run_date:
        repo.register_account(
            account_id,
            display_name=config.get("display_name") or config.get("account_id"),
            device_serial=config.get("device", {}).get("adb_serial"),
        )
        first_run_date = repo.get_first_run_date(account_id)

    last_run_date = repo.get_last_run_date(account_id)
    if force:
        last_run_date = None
        print("FORCE MODE: Bypassing one-session-per-day (testing only)")

    total_actions_today, likes_today = repo.get_today_totals(account_id)
    from src.health.monitor import is_in_cooldown
    in_cooldown = is_in_cooldown(account_id)

    from src.orchestrator.planner import build_plan

    plan = build_plan(
        first_run_date,
        last_run_date,
        today,
        total_actions_today,
        likes_today,
        in_cooldown,
        config,
    )

    if plan is None:
        if in_cooldown:
            from src.health.monitor import get_cooldown_until
            until = get_cooldown_until(account_id)
            print(f"Account is in cooldown until {until}.")
        elif one_session_per_day and not force and last_run_date == today:
            print("Already ran today. One session per day. Use status to see stats.")
        else:
            print("No plan for today.")
        return 0

    action_counts = {}
    for item in plan.items:
        action_counts[item.action.value] = action_counts.get(item.action.value, 0) + 1
    print(f"Plan: {len(plan.items)} actions")
    for action_type, count in action_counts.items():
        print(f"   - {action_type}: {count}")

    app_config = config.get("app", {})
    device_config = config.get("device", {})
    package = app_config.get("package", "com.zhiliaoapp.musically")
    activity = app_config.get("activity")
    adb_serial = device_config.get("adb_serial")

    from src.device.driver import create_driver, ensure_app_foreground
    from src.device.tiktok_app import TikTokApp

    try:
        driver = create_driver(package=package, activity=activity, adb_serial=adb_serial)
    except Exception as e:
        logger.error("Failed to create Appium driver: %s", e)
        print("Ensure Appium server is running and device/emulator is connected.")
        return 1

    ensure_app_foreground(driver, package)
    app = TikTokApp(driver)

    repo.set_last_run_date(account_id, today)
    from datetime import timezone
    session_started = __import__("datetime").datetime.now(timezone.utc)

    def on_action_done(action_type: str, count: int):
        repo.record_action(account_id, today, action_type, count)

    from src.warmup.runner import run_plan

    config_with_force = dict(config)
    config_with_force["force_mode"] = force

    def run():
        result = run_plan(
            plan,
            app,
            account_id,
            today,
            on_action_done=on_action_done,
            session_started_at=session_started,
            stop_flag=lambda: _stop_requested,
            config=config_with_force,
        )
        logger.info("Session finished: %s", result)

    _run_thread = threading.Thread(target=run)
    _run_thread.start()
    _run_thread.join()

    try:
        driver.quit()
    except Exception:
        pass

    print("Warm-up session finished. Use status to see totals.")
    return 0


def _cmd_stop() -> int:
    global _stop_requested
    _stop_requested = True
    print("Stop requested. Session will finish current action and exit.")
    return 0


def _cmd_select(account_id: str) -> int:
    _set_current_account(account_id)
    print(f"Selected account: {account_id}")
    return 0


def _clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def _print_menu():
    _clear_screen()
    print("\n" + "=" * 60)
    print("  TikTok Warm-Up Automation - Main Menu")
    print("=" * 60)
    print("  1. Auto Run (Full Warm-Up)")
    print("  2. View Status & Stats")
    print("  3. Config & Settings")
    print("  4. Account Management")
    print("  5. Stop Current Session")
    print("  6. Launch Web Interface (Posting Manager)")
    print("  0. Exit")
    print("=" * 60)
    print(f"Current Account: {_get_current_account()}")
    print("=" * 60)


def _menu_auto_run():
    print("\nAuto Run - Full Warm-Up")
    print("-" * 60)
    account_id = _get_current_account()
    ensure_schema()
    last_run = repo.get_last_run_date(account_id)
    today = __import__("datetime").date.today()
    if last_run == today:
        force = input("Already ran today. Force run? [y/N]: ").strip().lower() == "y"
        if not force:
            return 0
    else:
        force = False
    print("Starting warm-up (scroll FYP, like videos, visit profiles)...")
    confirm = input("Continue? [Y/n]: ").strip().lower()
    if confirm == "n":
        return 0
    return _cmd_start(account_id, force=force)


def _menu_web():
    print("\nLaunch Web Interface")
    print("Starting on http://127.0.0.1:5001")
    try:
        from web.app import app
        app.run(host="127.0.0.1", port=5001, debug=False)
    except KeyboardInterrupt:
        print("\nWeb interface stopped.")
    except Exception as e:
        logger.error("Failed to start web: %s", e)
        print(f"Error: {e}")


def _menu_config():
    print("\nConfig & Settings")
    print("-" * 60)
    account_id = _get_current_account()
    config = get_full_config(account_id)
    print(f"Account: {account_id}")
    print("Limits:", config.get("limits", {}))
    print("Warmup:", config.get("warmup", {}))
    print("Device:", config.get("device", {}))
    return 0


def _menu_accounts():
    print("\nAccount Management")
    print("-" * 60)
    ids_ = list_account_configs()
    if not ids_:
        print("No account configs. Add config/accounts/<id>.yaml (see example.yaml).")
        return 0
    current = _get_current_account()
    for i in ids_:
        mark = " (current)" if i == current else ""
        print(f"  {i}{mark}")
    sel = input("Select account (name or Enter to skip): ").strip()
    if sel:
        _cmd_select(sel)
    return 0


def main():
    if len(sys.argv) == 1:
        while True:
            _print_menu()
            choice = input("\nSelect option: ").strip()
            if choice == "0":
                print("Goodbye!")
                break
            elif choice == "1":
                _menu_auto_run()
            elif choice == "2":
                _cmd_status(_get_current_account())
            elif choice == "3":
                _menu_config()
            elif choice == "4":
                _menu_accounts()
            elif choice == "5":
                _cmd_stop()
            elif choice == "6":
                _menu_web()
            else:
                print("Invalid option.")
            if choice != "0":
                try:
                    input("\nPress Enter to continue...")
                except (EOFError, KeyboardInterrupt):
                    break
        return 0

    parser = argparse.ArgumentParser(description="TikTok Warm-Up CLI (manual login only)")
    sub = parser.add_subparsers(dest="command", required=True)
    start_p = sub.add_parser("start", help="Start warm-up session")
    start_p.add_argument("account_id", nargs="?", default=None)
    start_p.add_argument("--force", action="store_true", help="Force run even if already ran today")
    status_p = sub.add_parser("status", help="Show account status")
    status_p.add_argument("account_id", nargs="?", default=None)
    sub.add_parser("stop", help="Request stop of current session")
    sub.add_parser("list", help="List account configs")
    select_p = sub.add_parser("select", help="Select account")
    select_p.add_argument("account_id", help="Account id")
    args = parser.parse_args()

    if args.command == "start":
        aid = args.account_id or _get_current_account()
        return _cmd_start(aid, force=getattr(args, "force", False))
    if args.command == "status":
        aid = args.account_id or _get_current_account()
        return _cmd_status(aid)
    if args.command == "stop":
        return _cmd_stop()
    if args.command == "list":
        ids_ = list_account_configs()
        if not ids_:
            print("No account configs. Add config/accounts/<id>.yaml")
        else:
            current = _get_current_account()
            for i in ids_:
                mark = " (selected)" if i == current else ""
                print(f"{i}{mark}")
        return 0
    if args.command == "select":
        return _cmd_select(args.account_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
