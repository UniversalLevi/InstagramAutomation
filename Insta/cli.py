#!/usr/bin/env python3
"""
Instagram Warm-Up CLI. Run from project root.
Usage: 
  python cli.py                    # Interactive menu
  python cli.py start [account_id] # Command-line mode
Manual login only: log in to Instagram on the device once, then run start.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from pathlib import Path

# Ensure project root is on path
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

# Global stop flag for "stop" command (set by main when stop requested)
_stop_requested = False
_run_thread = None

CURRENT_ACCOUNT_FILE = PROJECT_ROOT / "data" / "current_account.txt"


def _get_current_account() -> str:
    """Return selected account id from data/current_account.txt, or 'default'."""
    if CURRENT_ACCOUNT_FILE.exists():
        try:
            return CURRENT_ACCOUNT_FILE.read_text(encoding="utf-8").strip() or "default"
        except Exception:
            pass
    return "default"


def _set_current_account(account_id: str) -> None:
    """Persist selected account for multi-account CLI."""
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
    # When --force is used, bypass one-session-per-day by pretending we haven't run today
    if force:
        last_run_date = None
        print("⚠️  FORCE MODE: Bypassing one-session-per-day restriction (testing only)")
    
    total_actions_today, likes_today = repo.get_today_totals(account_id)
    bio_edit_done = repo.get_bio_edit_done(account_id)

    from src.health.monitor import is_in_cooldown
    in_cooldown = is_in_cooldown(account_id)

    from src.orchestrator.planner import build_plan

    plan = build_plan(
        first_run_date,
        last_run_date,
        today,
        total_actions_today,
        likes_today,
        bio_edit_done,
        in_cooldown,
        config,
    )

    if plan is None:
        if in_cooldown:
            from src.health.monitor import get_cooldown_until
            until = get_cooldown_until(account_id)
            print(f"Account is in cooldown until {until}. Do not run until then.")
        elif one_session_per_day and not force and last_run_date == today:
            print("Already ran today. One session per day. Use status to see stats.")
            print("  Tip: Use --force to bypass for testing (not recommended for production)")
        else:
            print("No plan for today.")
        return 0

    # Show plan summary
    action_counts = {}
    for item in plan.items:
        action_counts[item.action.value] = action_counts.get(item.action.value, 0) + 1
    print(f"📋 Plan: {len(plan.items)} actions")
    for action_type, count in action_counts.items():
        print(f"   - {action_type}: {count}")

    # Device: create driver and app
    app_config = config.get("app", {})
    device_config = config.get("device", {})
    package = app_config.get("package", "com.instagram.android")
    # Don't specify activity - we'll use activate_app instead (more reliable with noReset=True)
    activity = app_config.get("activity")  # None by default
    adb_serial = device_config.get("adb_serial")

    from src.device.driver import create_driver
    from src.device.instagram_app import InstagramApp
    from src.device.driver import ensure_app_foreground

    try:
        driver = create_driver(package=package, activity=activity, adb_serial=adb_serial)
    except Exception as e:
        logger.error("Failed to create Appium driver: %s", e)
        print("Ensure Appium server is running (e.g. appium) and device/emulator is connected.")
        return 1

    ensure_app_foreground(driver, package)
    app = InstagramApp(driver)

    # Record last run date and session start
    repo.set_last_run_date(account_id, today)
    from datetime import timezone
    session_started = __import__("datetime").datetime.now(timezone.utc)

    def on_action_done(action_type: str, count: int):
        repo.record_action(account_id, today, action_type, count)

    from src.warmup.runner import run_plan

    # Pass force mode to runner (disables random early exit)
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
    print("Stop requested. Current session will finish current action and exit.")
    return 0


def _cmd_select(account_id: str) -> int:
    _set_current_account(account_id)
    print(f"Selected account: {account_id}")
    return 0


def _clear_screen():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def _print_menu():
    """Print main menu."""
    _clear_screen()
    print("\n" + "="*60)
    print("  📱 Instagram Warm-Up Automation - Main Menu")
    print("="*60)
    print("  1. 🚀 Auto Run Everything (Full Warm-Up)")
    print("  2. 🎯 Selective Run (Choose Actions)")
    print("  3. ⚙️  Config & Settings")
    print("  4. 📊 View Status & Stats")
    print("  5. 🔧 Customize Warm-Up Behavior")
    print("  6. 📝 Account Management")
    print("  7. 🛑 Stop Current Session")
    print("  8. 🌐 Launch Web Interface (Posting Manager)")
    print("  0. ❌ Exit")
    print("="*60)
    print(f"Current Account: {_get_current_account()}")
    print("="*60)


def _menu_auto_run():
    """Option 1: Auto run everything."""
    print("\n🚀 Auto Run Everything")
    print("-" * 60)
    account_id = _get_current_account()
    print(f"Account: {account_id}")
    
    # Check if already ran today
    ensure_schema()
    last_run = repo.get_last_run_date(account_id)
    today = __import__("datetime").date.today()
    if last_run == today:
        print("⚠️  Already ran today. Use force mode to run again.")
        force = input("Force run (bypass daily limit)? [y/N]: ").strip().lower() == 'y'
        if not force:
            print("Cancelled.")
            return 0
    else:
        force = False
    
    print("\nStarting full warm-up session...")
    print("This will:")
    print("  • Navigate to Reels")
    print("  • Scroll through videos")
    print("  • Like 3-4 Reels randomly")
    print("  • Visit profiles")
    print("  • Like posts")
    print("  • Go to own profile")
    
    confirm = input("\nContinue? [Y/n]: ").strip().lower()
    if confirm == 'n':
        print("Cancelled.")
        return 0
    
    return _cmd_start(account_id, force=force)


def _menu_selective_run():
    """Option 2: Selective run with sub-options."""
    print("\n🎯 Selective Run - Choose Actions")
    print("-" * 60)
    
    actions = {
        '1': ('scroll_reels', 'Scroll Reels', 'Scroll through Reels videos'),
        '2': ('like_reels', 'Like Reels (3-4)', 'Like 3-4 Reel videos randomly'),
        '3': ('scroll_feed', 'Scroll Feed (UP)', 'Scroll feed upward'),
        '4': ('like_posts', 'Like Posts', 'Like regular posts'),
        '5': ('visit_profiles', 'Visit Profiles', 'Visit profiles from feed'),
        '6': ('go_to_profile', 'Go to Own Profile', 'Navigate to your profile'),
    }
    
    print("\nSelect actions to run (comma-separated, e.g., 1,2,3):")
    for key, (_, desc, _) in actions.items():
        print(f"  {key}. {desc}")
    print("  a. All actions")
    print("  0. Cancel")
    
    choice = input("\nYour choice: ").strip().lower()
    
    if choice == '0':
        print("Cancelled.")
        return 0
    
    if choice == 'a':
        print("\nRunning all actions...")
        account_id = _get_current_account()
        return _cmd_start(account_id, force=True)
    
    selected = [actions[c][0] for c in choice.split(',') if c.strip() in actions]
    if not selected:
        print("❌ No valid actions selected.")
        return 1
    
    print(f"\n✅ Selected actions:")
    for c in choice.split(','):
        c = c.strip()
        if c in actions:
            print(f"   • {actions[c][1]}: {actions[c][2]}")
    
    print("\n⚠️  Note: Selective run uses force mode to bypass daily limits")
    confirm = input("Continue? [Y/n]: ").strip().lower()
    if confirm == 'n':
        print("Cancelled.")
        return 0
    
    # For now, run full warmup (selective filtering can be added later)
    account_id = _get_current_account()
    return _cmd_start(account_id, force=True)


def _menu_config_settings():
    """Option 3: Config & Settings."""
    print("\n⚙️  Config & Settings")
    print("-" * 60)
    
    while True:
        print("\nConfig Options:")
        print("  1. View Current Config")
        print("  2. Edit Delay Settings")
        print("  3. Edit Scroll Duration")
        print("  4. Edit Daily Limits")
        print("  5. View Account Config")
        print("  0. Back to Main Menu")
        
        choice = input("\nYour choice: ").strip()
        
        if choice == '0':
            break
        elif choice == '1':
            _show_current_config()
        elif choice == '2':
            _edit_delay_settings()
        elif choice == '3':
            _edit_scroll_duration()
        elif choice == '4':
            _edit_daily_limits()
        elif choice == '5':
            _show_account_config()
        else:
            print("❌ Invalid choice.")
    
    return 0


def _show_current_config():
    """Show current configuration."""
    account_id = _get_current_account()
    config = get_full_config(account_id)
    
    print("\n📋 Current Configuration:")
    print(f"Account: {account_id}")
    print(f"\nLimits:")
    limits = config.get("limits", {})
    print(f"  Max actions/day: {limits.get('max_actions_per_day', 'N/A')}")
    print(f"  Max likes/day (first 2 weeks): {limits.get('max_likes_per_day_first_two_weeks', 'N/A')}")
    print(f"  Max session minutes: {limits.get('max_session_minutes', 'N/A')}")
    
    print(f"\nWarmup:")
    warmup = config.get("warmup", {})
    print(f"  Delay between actions: {warmup.get('delay_between_actions_min', 'N/A')}-{warmup.get('delay_between_actions_max', 'N/A')}s")
    print(f"  Scroll duration: {warmup.get('scroll_duration_min_sec', 'N/A')}-{warmup.get('scroll_duration_max_sec', 'N/A')}s")
    
    print(f"\nDevice:")
    device = config.get("device", {})
    print(f"  ADB Serial: {device.get('adb_serial', 'Not set')}")


def _edit_delay_settings():
    """Edit delay settings."""
    print("\n⏱️  Edit Delay Settings")
    print("(Note: Changes are saved to config/accounts/[account].yaml)")
    
    min_delay = input("Min delay between actions (seconds) [2]: ").strip()
    max_delay = input("Max delay between actions (seconds) [8]: ").strip()
    
    print("⚠️  To persist changes, edit config/accounts/[account].yaml manually")
    print("   Or use: warmup.delay_between_actions_min and delay_between_actions_max")


def _edit_scroll_duration():
    """Edit scroll duration."""
    print("\n📜 Edit Scroll Duration")
    print("(Note: Changes are saved to config/accounts/[account].yaml)")
    
    min_scroll = input("Min scroll duration (seconds) [30]: ").strip()
    max_scroll = input("Max scroll duration (seconds) [60]: ").strip()
    
    print("⚠️  To persist changes, edit config/accounts/[account].yaml manually")
    print("   Or use: warmup.scroll_duration_min_sec and scroll_duration_max_sec")


def _edit_daily_limits():
    """Edit daily limits."""
    print("\n📊 Edit Daily Limits")
    print("(Note: Changes are saved to config/accounts/[account].yaml)")
    
    max_actions = input("Max actions per day [10]: ").strip()
    max_likes = input("Max likes per day (first 2 weeks) [5]: ").strip()
    max_minutes = input("Max session minutes [15]: ").strip()
    
    print("⚠️  To persist changes, edit config/accounts/[account].yaml manually")
    print("   Or use: limits.max_actions_per_day, max_likes_per_day_first_two_weeks, max_session_minutes")


def _show_account_config():
    """Show account-specific config."""
    account_id = _get_current_account()
    config = get_full_config(account_id)
    
    print(f"\n👤 Account Config: {account_id}")
    print(f"Display Name: {config.get('display_name', 'N/A')}")
    print(f"Device Serial: {config.get('device', {}).get('adb_serial', 'Not set')}")
    print(f"App Package: {config.get('app', {}).get('package', 'N/A')}")


def _menu_customize():
    """Option 5: Customize warm-up behavior."""
    print("\n🔧 Customize Warm-Up Behavior")
    print("-" * 60)
    
    while True:
        print("\nCustomization Options:")
        print("  1. Set Reels Likes Count (3-4)")
        print("  2. Set Scroll Speed")
        print("  3. Enable/Disable Randomization")
        print("  4. Set Action Probabilities")
        print("  0. Back to Main Menu")
        
        choice = input("\nYour choice: ").strip()
        
        if choice == '0':
            break
        elif choice == '1':
            count = input("Number of Reels to like (3-4) [4]: ").strip()
            print(f"⚠️  To persist: edit planner.py DEFAULT_DAY_BANDS")
        elif choice == '2':
            speed = input("Scroll speed (fast/normal/slow) [normal]: ").strip()
            print(f"⚠️  To persist: edit config defaults.yaml warmup settings")
        elif choice == '3':
            enable = input("Enable randomization? [y/N]: ").strip().lower() == 'y'
            print(f"⚠️  Randomization is always enabled in current implementation")
        elif choice == '4':
            print("⚠️  Action probabilities are hardcoded in runner.py")
            print("   - VISIT_PROFILE: 10% skip chance")
            print("   - LIKE_POST: 15% skip chance")
            print("   - LIKE_REEL: 20% skip chance")
        else:
            print("❌ Invalid choice.")
    
    return 0


def _menu_web_interface():
    """Option 8: Launch web interface."""
    print("\n🌐 Launch Web Interface")
    print("-" * 60)
    print("Starting web interface on http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    print("\nFeatures:")
    print("  • Upload media (photos, videos, reels, carousels)")
    print("  • Add captions and hashtags")
    print("  • Schedule posts")
    print("  • Manage posting queue")
    print("  • View statistics")
    
    try:
        from web.app import app
        app.run(host="127.0.0.1", port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n\nWeb interface stopped.")
    except Exception as e:
        logger.error("Failed to start web interface: %s", e)
        print(f"\n❌ Error: {e}")
        print("Make sure Flask is installed: pip install Flask")


def _menu_account_management():
    """Option 6: Account Management."""
    print("\n📝 Account Management")
    print("-" * 60)
    
    while True:
        print("\nAccount Options:")
        print("  1. List Accounts")
        print("  2. Select Account")
        print("  3. View Account Status")
        print("  4. Create New Account Config")
        print("  0. Back to Main Menu")
        
        choice = input("\nYour choice: ").strip()
        
        if choice == '0':
            break
        elif choice == '1':
            ids_ = list_account_configs()
            if not ids_:
                print("No account configs found.")
            else:
                current = _get_current_account()
                print("\nAccounts:")
                for i in ids_:
                    mark = " ← Current" if i == current else ""
                    print(f"  • {i}{mark}")
        elif choice == '2':
            ids_ = list_account_configs()
            if ids_:
                print("\nAvailable accounts:")
                for idx, acc_id in enumerate(ids_, 1):
                    print(f"  {idx}. {acc_id}")
                sel = input("\nSelect account (number or name): ").strip()
                try:
                    if sel.isdigit():
                        account_id = ids_[int(sel) - 1]
                    else:
                        account_id = sel
                    _cmd_select(account_id)
                except (IndexError, ValueError):
                    print("❌ Invalid selection.")
            else:
                print("No accounts available.")
        elif choice == '3':
            account_id = _get_current_account()
            _cmd_status(account_id)
        elif choice == '4':
            print("⚠️  To create a new account config:")
            print("   1. Copy config/accounts/example.yaml to config/accounts/[account_id].yaml")
            print("   2. Edit the file and set device.adb_serial")
            print("   3. Use option 2 to select the new account")
        else:
            print("❌ Invalid choice.")
    
    return 0


def main():
    # If no arguments provided, show interactive menu
    if len(sys.argv) == 1:
        while True:
            _print_menu()
            choice = input("\nSelect an option: ").strip()
            
            if choice == '0':
                print("\n👋 Goodbye!")
                break
            elif choice == '1':
                _menu_auto_run()
            elif choice == '2':
                _menu_selective_run()
            elif choice == '3':
                _menu_config_settings()
            elif choice == '4':
                account_id = _get_current_account()
                _cmd_status(account_id)
            elif choice == '5':
                _menu_customize()
            elif choice == '6':
                _menu_account_management()
            elif choice == '7':
                _cmd_stop()
            elif choice == '8':
                _menu_web_interface()
            else:
                print("❌ Invalid option. Please try again.")
            
            if choice != '0':
                try:
                    input("\nPress Enter to return to menu...")
                except (EOFError, KeyboardInterrupt):
                    break
    
    else:
        # Original argparse functionality for command-line usage
        parser = argparse.ArgumentParser(description="Instagram Warm-Up CLI (manual login only)")
        sub = parser.add_subparsers(dest="command", required=True)
        start_p = sub.add_parser("start", help="Start warm-up session")
        start_p.add_argument("account_id", nargs="?", default=None, help="Account id (default: selected or 'default')")
        start_p.add_argument("--force", action="store_true", help="Force run even if already ran today (testing only)")
        status_p = sub.add_parser("status", help="Show account status")
        status_p.add_argument("account_id", nargs="?", default=None, help="Account id")
        sub.add_parser("stop", help="Request stop of current session")
        sub.add_parser("list", help="List account configs")
        select_p = sub.add_parser("select", help="Select account for start/status when omitted")
        select_p.add_argument("account_id", help="Account id to select")
        args = parser.parse_args()

        if args.command == "start":
            aid = args.account_id if args.account_id is not None else _get_current_account()
            return _cmd_start(aid, force=getattr(args, "force", False))
        if args.command == "status":
            aid = args.account_id if args.account_id is not None else _get_current_account()
            return _cmd_status(aid)
        if args.command == "stop":
            return _cmd_stop()
        if args.command == "list":
            ids_ = list_account_configs()
            if not ids_:
                print("No account configs found. Add a YAML file under config/accounts/ (see example.yaml).")
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
