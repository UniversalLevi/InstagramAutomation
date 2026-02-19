"""
Account health: cooldown on block/warning. Uses TikTok state DB.
"""
from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def set_cooldown(
    account_id: str,
    cooldown_days_min: int = 3,
    cooldown_days_max: int = 7,
    incident_type: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> date:
    days = random.randint(cooldown_days_min, cooldown_days_max)
    until = date.today() + timedelta(days=days)
    now = datetime.utcnow().isoformat() + "Z"
    from state.db import get_connection, init_schema

    init_schema(db_path=db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO health (account_id, cooldown_until_date, last_incident_at, incident_type, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                cooldown_until_date = excluded.cooldown_until_date,
                last_incident_at = excluded.last_incident_at,
                incident_type = excluded.incident_type,
                updated_at = excluded.updated_at
            """,
            (account_id, until.isoformat(), now, incident_type or "block", now, now),
        )
        conn.commit()
    finally:
        conn.close()
    logger.warning("Health: cooldown set until %s for account %s", until, account_id)
    return until


def get_cooldown_until(account_id: str, db_path: Optional[Path] = None) -> Optional[date]:
    from state.db import get_connection, init_schema

    init_schema(db_path=db_path)
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "SELECT cooldown_until_date FROM health WHERE account_id = ?",
            (account_id,),
        )
        row = cur.fetchone()
        if row and row[0]:
            d = date.fromisoformat(row[0])
            if d >= date.today():
                return d
            return None
        return None
    finally:
        conn.close()


def is_in_cooldown(account_id: str, db_path: Optional[Path] = None) -> bool:
    return get_cooldown_until(account_id, db_path) is not None


def clear_cooldown(account_id: str, db_path: Optional[Path] = None) -> None:
    from state.db import get_connection

    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE health SET cooldown_until_date = NULL, updated_at = ? WHERE account_id = ?",
            (datetime.utcnow().isoformat() + "Z", account_id),
        )
        conn.commit()
    finally:
        conn.close()
