"""Storage helpers for Telegram user chat bindings."""

from datetime import datetime
from typing import Optional


_DEP_NAMES = (
    "DB_PATH",
    "TZ",
    "sqlite3",
)


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def upsert_user_chat_impl(user_id: int, chat_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str], *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('\n        INSERT INTO user_chats(user_id, chat_id, username, first_name, last_name, updated_at)\n        VALUES (?, ?, ?, ?, ?, ?)\n        ON CONFLICT(user_id) DO UPDATE SET\n            chat_id = excluded.chat_id,\n            username = excluded.username,\n            first_name = excluded.first_name,\n            last_name = excluded.last_name,\n            updated_at = excluded.updated_at\n        ', (user_id, chat_id, (username or '').lower() if username else None, first_name, last_name, datetime.now(TZ).isoformat()))
    conn.commit()
    conn.close()


def get_user_chat_id_by_username_impl(username: str, *, deps) -> Optional[int]:
    _apply_deps(deps)
    uname = username.strip().lstrip('@').lower()
    if not uname:
        return None
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT chat_id FROM user_chats WHERE username = ? ORDER BY updated_at DESC LIMIT 1', (uname,))
    row = c.fetchone()
    conn.close()
    if row:
        return int(row[0])
    return None


def get_user_chat_id_by_user_id_impl(user_id: int, *, deps) -> Optional[int]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT chat_id FROM user_chats WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return int(row[0])
    return None
