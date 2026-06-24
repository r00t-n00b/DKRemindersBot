"""Storage helpers for reminder nudges."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


_DEP_NAMES = (
    "DB_PATH",
    "sqlite3",
)


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def _nudge_threshold_minutes_impl(nudge_count: int) -> Optional[int]:
    thresholds = [20, 80, 320, 1040]
    if 0 <= nudge_count < len(thresholds):
        return thresholds[nudge_count]
    return None


def get_due_nudges_impl(now: datetime, *, deps) -> List[Dict[str, Any]]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute('\n            SELECT id, chat_id, text, sent_at, nudge_count\n            FROM reminders\n            WHERE delivered = 1\n              AND acked = 0\n              AND nudge_count < 4\n              AND sent_at IS NOT NULL\n            ').fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                sent_at = datetime.fromisoformat(r['sent_at'])
            except Exception:
                continue
            threshold = _nudge_threshold_minutes_impl(int(r['nudge_count']))
            if threshold is None:
                continue
            if now >= sent_at + timedelta(minutes=threshold):
                out.append(dict(r))
        return out
    finally:
        conn.close()


def increment_nudge_count_impl(reminder_id: int, *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('UPDATE reminders SET nudge_count = nudge_count + 1 WHERE id = ?', (reminder_id,))
        conn.commit()
    finally:
        conn.close()


def exhaust_nudges_impl(reminder_id: int, *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('UPDATE reminders SET nudge_count = 4 WHERE id = ?', (reminder_id,))
        conn.commit()
    finally:
        conn.close()
