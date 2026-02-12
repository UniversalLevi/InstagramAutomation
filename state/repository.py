"""
Repository layer for account state: first_run_date, last_run_date, action counts, health.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

from . import db as db_module


def register_account(
    account_id: str,
    display_name: Optional[str] = None,
    device_serial: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    today = date.today().isoformat()
    now = datetime.utcnow().isoformat() + "Z"
    with db_module.cursor(db_path) as cur:
        cur.execute(
            """
            INSERT OR IGNORE INTO account
            (account_id, display_name, device_serial, first_run_date, last_run_date, bio_edit_done, created_at, updated_at)
            VALUES (?, ?, ?, ?, NULL, 0, ?, ?)
            """,
            (account_id, display_name or account_id, device_serial, today, now, now),
        )
        if cur.rowcount == 0:
            cur.execute(
                "UPDATE account SET display_name = ?, device_serial = COALESCE(?, device_serial), updated_at = ? WHERE account_id = ?",
                (display_name or account_id, device_serial, now, account_id),
            )


def get_account(account_id: str, db_path: Optional[Path] = None) -> Optional[dict]:
    with db_module.cursor(db_path) as cur:
        cur.execute("SELECT * FROM account WHERE account_id = ?", (account_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_first_run_date(account_id: str, db_path: Optional[Path] = None) -> Optional[date]:
    acc = get_account(account_id, db_path)
    if not acc or not acc.get("first_run_date"):
        return None
    return date.fromisoformat(acc["first_run_date"])


def get_last_run_date(account_id: str, db_path: Optional[Path] = None) -> Optional[date]:
    acc = get_account(account_id, db_path)
    if not acc or not acc.get("last_run_date"):
        return None
    return date.fromisoformat(acc["last_run_date"])


def set_last_run_date(account_id: str, run_date: date, db_path: Optional[Path] = None) -> None:
    now = datetime.utcnow().isoformat() + "Z"
    with db_module.cursor(db_path) as cur:
        cur.execute(
            "UPDATE account SET last_run_date = ?, updated_at = ? WHERE account_id = ?",
            (run_date.isoformat(), now, account_id),
        )


def get_bio_edit_done(account_id: str, db_path: Optional[Path] = None) -> bool:
    acc = get_account(account_id, db_path)
    return bool(acc and acc.get("bio_edit_done"))


def set_bio_edit_done(account_id: str, db_path: Optional[Path] = None) -> None:
    now = datetime.utcnow().isoformat() + "Z"
    with db_module.cursor(db_path) as cur:
        cur.execute(
            "UPDATE account SET bio_edit_done = 1, updated_at = ? WHERE account_id = ?",
            (now, account_id),
        )


def record_action(
    account_id: str,
    run_date: date,
    action_type: str,
    count: int = 1,
    db_path: Optional[Path] = None,
) -> None:
    now = datetime.utcnow().isoformat() + "Z"
    with db_module.cursor(db_path) as cur:
        cur.execute(
            "INSERT INTO action_history (account_id, run_date, action_type, count, created_at) VALUES (?, ?, ?, ?, ?)",
            (account_id, run_date.isoformat(), action_type, count, now),
        )


def get_today_totals(account_id: str, db_path: Optional[Path] = None) -> Tuple[int, int]:
    """Returns (total_actions, likes_count) for today."""
    today = date.today().isoformat()
    with db_module.cursor(db_path) as cur:
        cur.execute(
            "SELECT total_actions, likes_count FROM daily_totals WHERE account_id = ? AND run_date = ?",
            (account_id, today),
        )
        row = cur.fetchone()
        if row:
            return row["total_actions"], row["likes_count"]
    return 0, 0


def upsert_daily_totals(
    account_id: str,
    run_date: date,
    total_actions: int,
    likes_count: int,
    session_started_at: Optional[str] = None,
    session_ended_at: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    with db_module.cursor(db_path) as cur:
        cur.execute(
            """
            INSERT INTO daily_totals (account_id, run_date, total_actions, likes_count, session_started_at, session_ended_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, run_date) DO UPDATE SET
                total_actions = excluded.total_actions,
                likes_count = excluded.likes_count,
                session_started_at = COALESCE(excluded.session_started_at, session_started_at),
                session_ended_at = COALESCE(excluded.session_ended_at, session_ended_at)
            """,
            (account_id, run_date.isoformat(), total_actions, likes_count, session_started_at, session_ended_at),
        )


def get_actions_today(account_id: str, db_path: Optional[Path] = None) -> List[dict]:
    today = date.today().isoformat()
    with db_module.cursor(db_path) as cur:
        cur.execute(
            "SELECT action_type, count FROM action_history WHERE account_id = ? AND run_date = ?",
            (account_id, today),
        )
        return [dict(r) for r in cur.fetchall()]


def increment_daily_totals(
    account_id: str,
    run_date: date,
    actions_delta: int,
    likes_delta: int,
    session_started_at: Optional[str] = None,
    session_ended_at: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    total, likes = get_today_totals(account_id, db_path)
    total += actions_delta
    likes += likes_delta
    upsert_daily_totals(
        account_id, run_date, total, likes,
        session_started_at=session_started_at,
        session_ended_at=session_ended_at,
        db_path=db_path,
    )
