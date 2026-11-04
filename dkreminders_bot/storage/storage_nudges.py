"""Storage helpers for reminder nudges."""

from datetime import datetime, timezone

from dkreminders_bot.domain.nudge_policy import DEFAULT_GAPS, nudge_due
from dkreminders_bot.storage.settings_store import nudge_settings
from typing import Any, Dict, List, Optional


_DEP_NAMES = (
    "DB_PATH",
    "sqlite3",
)


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def _nudge_threshold_minutes_impl(nudge_count: int) -> Optional[int]:
    thresholds = [sum(DEFAULT_GAPS[:i+1]) for i in range(len(DEFAULT_GAPS))]
    if 0 <= nudge_count < len(thresholds):
        return thresholds[nudge_count]
    return None


def get_due_nudges_impl(now: datetime, *, deps) -> List[Dict[str, Any]]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM reminders WHERE delivered = 1 AND acked = 0 AND sent_at IS NOT NULL").fetchall()
        configs = {}
        result = []
        for row in rows:
            r = dict(row)
            chat_id = r["chat_id"]
            if chat_id not in configs:
                configs[chat_id] = nudge_settings(conn, chat_id)
            if nudge_due(r, configs[chat_id], now):
                result.append(r)
        return result
    finally:
        conn.close()


def can_send_nudge_impl(reminder_id: int, now: datetime, *, deps) -> bool:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()
        return bool(row and nudge_due(dict(row), nudge_settings(conn, row["chat_id"]), now))
    finally:
        conn.close()


def increment_nudge_count_impl(reminder_id: int, *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(reminders)")}
        if "last_nudge_at" in cols:
            clock = getattr(deps, "get_now", lambda: datetime.now(timezone.utc))
            conn.execute("UPDATE reminders SET nudge_count = nudge_count + 1, last_nudge_at = ? WHERE id = ?", (clock().isoformat(), reminder_id))
        else:
            conn.execute("UPDATE reminders SET nudge_count = nudge_count + 1 WHERE id = ?", (reminder_id,))
        conn.commit()
    finally:
        conn.close()


def exhaust_nudges_impl(reminder_id: int, *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(reminders)")}
        if "nudge_exhausted" in cols:
            conn.execute("UPDATE reminders SET nudge_exhausted = 1 WHERE id = ?", (reminder_id,))
        else:
            conn.execute("UPDATE reminders SET nudge_count = 4 WHERE id = ?", (reminder_id,))
        conn.commit()
    finally:
        conn.close()
