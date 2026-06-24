"""Write-only storage helpers for reminder creation/update/mark operations."""

from datetime import datetime
from typing import Any, Dict, Optional


_DEP_NAMES = (
    "DB_PATH",
    "TZ",
    "get_now",
    "json",
    "sqlite3",
)


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def add_reminder_impl(chat_id: int, text: str, remind_at: datetime, created_by: Optional[int], template_id: Optional[int]=None, *, deps) -> int:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('\n        INSERT INTO reminders (chat_id, text, remind_at, created_by, created_at, delivered, template_id)\n        VALUES (?, ?, ?, ?, ?, 0, ?)\n        ', (chat_id, text, remind_at.isoformat(), created_by, datetime.now(TZ).isoformat(), template_id))
    reminder_id = c.lastrowid
    conn.commit()
    conn.close()
    return reminder_id


def update_reminder_time_impl(reminder_id: int, new_dt: datetime, *, deps) -> bool:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('\n        UPDATE reminders\n        SET remind_at = ?,\n            delivered = 0,\n            acked = 0,\n            sent_at = NULL,\n            nudge_count = 0\n        WHERE id = ?\n        ', (new_dt.isoformat(), int(reminder_id)))
    changed = c.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def mark_reminder_sent_impl(reminder_id: int, sent_at: Optional[datetime]=None, *, deps) -> None:
    _apply_deps(deps)
    if sent_at is None:
        sent_at = get_now()
    if isinstance(sent_at, str):
        sent_at = datetime.fromisoformat(sent_at)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('\n            UPDATE reminders\n            SET delivered = 1,\n                sent_at = ?,\n                acked = 0\n            WHERE id = ?\n            ', (sent_at.isoformat(), reminder_id))
        conn.commit()
    finally:
        conn.close()


def mark_reminder_acked_impl(reminder_id: int, *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE reminders SET acked = 1 WHERE id = ?', (reminder_id,))
    conn.commit()
    conn.close()


def mark_nudge_sent_impl(reminder_id: int, *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE reminders SET nudge_sent = 1 WHERE id = ?', (reminder_id,))
    conn.commit()
    conn.close()


def create_recurring_template_impl(chat_id: int, text: str, pattern_type: str, payload: Dict[str, Any], time_hour: int, time_minute: int, created_by: Optional[int], *, deps) -> int:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('\n        INSERT INTO recurring_templates\n            (chat_id, text, pattern_type, payload, time_hour, time_minute, created_by, created_at, active)\n        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)\n        ', (chat_id, text, pattern_type, json.dumps(payload, ensure_ascii=False), time_hour, time_minute, created_by, datetime.now(TZ).isoformat()))
    tpl_id = c.lastrowid
    conn.commit()
    conn.close()
    return tpl_id
