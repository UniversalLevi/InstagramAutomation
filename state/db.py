"""
SQLite state: account, action_history, daily_totals, health/cooldown.
One DB per account or single DB with account_id; we use single DB with account_id for multi-account.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Generator, Optional

# Default DB path relative to project root
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "warmup.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def cursor(db_path: Optional[Path] = None) -> Generator[sqlite3.Cursor, None, None]:
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        finally:
            cur.close()
    finally:
        conn.close()


def init_schema(conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> None:
    """Create tables if they do not exist."""
    if conn is None:
        conn = get_connection(db_path)
        try:
            _init_schema_impl(conn)
            conn.commit()
        finally:
            conn.close()
    else:
        _init_schema_impl(conn)


def _init_schema_impl(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS account (
            account_id TEXT PRIMARY KEY,
            display_name TEXT,
            device_serial TEXT,
            first_run_date TEXT NOT NULL,
            last_run_date TEXT,
            bio_edit_done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS action_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT NOT NULL,
            run_date TEXT NOT NULL,
            action_type TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES account(account_id)
        );

        CREATE TABLE IF NOT EXISTS daily_totals (
            account_id TEXT NOT NULL,
            run_date TEXT NOT NULL,
            total_actions INTEGER NOT NULL DEFAULT 0,
            likes_count INTEGER NOT NULL DEFAULT 0,
            session_started_at TEXT,
            session_ended_at TEXT,
            PRIMARY KEY (account_id, run_date),
            FOREIGN KEY (account_id) REFERENCES account(account_id)
        );

        CREATE TABLE IF NOT EXISTS health (
            account_id TEXT PRIMARY KEY,
            cooldown_until_date TEXT,
            last_incident_at TEXT,
            incident_type TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES account(account_id)
        );

        CREATE INDEX IF NOT EXISTS idx_action_history_account_date
            ON action_history(account_id, run_date);
        CREATE INDEX IF NOT EXISTS idx_daily_totals_account
            ON daily_totals(account_id);
    """)


def ensure_schema(db_path: Optional[Path] = None) -> None:
    """Ensure DB file and schema exist."""
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    init_schema(db_path=path)
