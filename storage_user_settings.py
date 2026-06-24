"""Storage helpers for per-user settings."""

from typing import Optional, Tuple


_DEP_NAMES = (
    "DB_PATH",
    "get_now",
    "sqlite3",
)


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def get_user_default_time_impl(user_id: Optional[int], *, deps) -> Optional[Tuple[int, int]]:
    _apply_deps(deps)
    if user_id is None:
        return None
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute('\n            SELECT default_hour, default_minute\n            FROM user_settings\n            WHERE user_id = ?\n            ', (int(user_id),)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    hour, minute = row
    if hour is None or minute is None:
        return None
    try:
        return (int(hour), int(minute))
    except Exception:
        return None


def set_user_default_time_impl(user_id: int, hour: int, minute: int, *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('\n            INSERT INTO user_settings(user_id, default_hour, default_minute, updated_at)\n            VALUES (?, ?, ?, ?)\n            ON CONFLICT(user_id) DO UPDATE SET\n                default_hour = excluded.default_hour,\n                default_minute = excluded.default_minute,\n                updated_at = excluded.updated_at\n            ', (int(user_id), int(hour), int(minute), get_now().isoformat()))
        conn.commit()
    finally:
        conn.close()


def clear_user_default_time_impl(user_id: int, *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute('DELETE FROM user_settings WHERE user_id = ?', (int(user_id),))
        conn.commit()
    finally:
        conn.close()
