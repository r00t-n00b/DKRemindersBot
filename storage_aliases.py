"""Storage helpers for chat/user aliases."""
from time_utils import aware_now

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import sqlite3


_DEP_NAMES = (
    "DB_PATH",
    "TZ",
    "sqlite3",
)


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def _find_existing_alias_casefold(
    c: sqlite3.Cursor,
    table: str,
    alias: str,
    created_by: int,
) -> Optional[str]:
    target = alias.casefold()

    c.execute(
        f"""
        SELECT alias
        FROM {table}
        WHERE created_by = ?
        """,
        (created_by,),
    )

    for row in c.fetchall():
        existing_alias = str(row[0])
        if existing_alias.casefold() == target:
            return existing_alias

    return None


def set_chat_alias_impl(alias: str, chat_id: int, title: Optional[str], created_by: int=0, *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing_alias = _find_existing_alias_casefold(c, 'chat_aliases', alias, created_by)
    if existing_alias is not None:
        c.execute('\n            UPDATE chat_aliases\n            SET chat_id = ?, title = ?\n            WHERE alias = ? AND created_by = ?\n            ', (chat_id, title, existing_alias, created_by))
    else:
        c.execute('\n            INSERT INTO chat_aliases(alias, chat_id, title, created_by)\n            VALUES (?, ?, ?, ?)\n            ', (alias, chat_id, title, created_by))
    conn.commit()
    conn.close()


def get_chat_id_by_alias_impl(alias: str, created_by: int=0, *, deps) -> Optional[int]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing_alias = _find_existing_alias_casefold(c, 'chat_aliases', alias, created_by)
    if existing_alias is None:
        conn.close()
        return None
    c.execute('\n        SELECT chat_id\n        FROM chat_aliases\n        WHERE alias = ? AND created_by = ?\n        ', (existing_alias, created_by))
    row = c.fetchone()
    conn.close()
    if row:
        return int(row[0])
    return None


def get_all_aliases_impl(created_by: int, *, deps):
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('\n        SELECT alias, chat_id, title\n        FROM chat_aliases\n        WHERE created_by = ?\n        ORDER BY alias COLLATE NOCASE\n        ', (created_by,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_user_alias_impl(alias: str, created_by: int, *, deps) -> Optional[Dict[str, Any]]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    existing_alias = _find_existing_alias_casefold(c, 'user_aliases', alias, created_by)
    if existing_alias is None:
        conn.close()
        return None
    c.execute('\n        SELECT alias, user_id, chat_id, username, created_by, created_at\n        FROM user_aliases\n        WHERE alias = ? AND created_by = ?\n        ', (existing_alias, created_by))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def set_user_alias_impl(alias: str, user_id: int, chat_id: int, username: Optional[str], created_by: int, *, deps) -> None:
    _apply_deps(deps)
    now_iso = aware_now(TZ).isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing_alias = _find_existing_alias_casefold(c, 'user_aliases', alias, created_by)
    if existing_alias is not None:
        c.execute('\n            UPDATE user_aliases\n            SET user_id = ?, chat_id = ?, username = ?, created_at = ?\n            WHERE alias = ? AND created_by = ?\n            ', (user_id, chat_id, username, now_iso, existing_alias, created_by))
    else:
        c.execute('\n            INSERT INTO user_aliases(alias, user_id, chat_id, username, created_by, created_at)\n            VALUES (?, ?, ?, ?, ?, ?)\n            ', (alias, user_id, chat_id, username, created_by, now_iso))
    conn.commit()
    conn.close()


def get_user_alias_chat_id_impl(alias: str, created_by: int=0, *, deps) -> Optional[int]:
    _apply_deps(deps)
    row = get_user_alias_impl(alias, created_by, deps=deps)
    if not row:
        return None
    return int(row['chat_id'])


def get_all_user_aliases_impl(created_by: int, *, deps) -> List[Tuple[str, int]]:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('\n        SELECT alias, chat_id\n        FROM user_aliases\n        WHERE created_by = ?\n        ORDER BY alias COLLATE NOCASE\n        ', (created_by,))
    rows = c.fetchall()
    conn.close()
    return [(str(alias), int(chat_id)) for alias, chat_id in rows]


def delete_chat_alias_impl(alias: str, created_by: int, *, deps) -> bool:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing_alias = _find_existing_alias_casefold(c, 'chat_aliases', alias, created_by)
    if existing_alias is None:
        conn.close()
        return False
    c.execute('DELETE FROM chat_aliases WHERE alias = ? AND created_by = ?', (existing_alias, created_by))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def delete_user_alias_impl(alias: str, created_by: int, *, deps) -> bool:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing_alias = _find_existing_alias_casefold(c, 'user_aliases', alias, created_by)
    if existing_alias is None:
        conn.close()
        return False
    c.execute('DELETE FROM user_aliases WHERE alias = ? AND created_by = ?', (existing_alias, created_by))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def rename_chat_alias_impl(old_alias: str, new_alias: str, created_by: int, *, deps) -> bool:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing_old_alias = _find_existing_alias_casefold(c, 'chat_aliases', old_alias, created_by)
    if existing_old_alias is None:
        conn.close()
        return False
    if old_alias.casefold() != new_alias.casefold():
        if _find_existing_alias_casefold(c, 'chat_aliases', new_alias, created_by) is not None:
            conn.close()
            raise ValueError(f"Chat-alias '{new_alias}' уже существует")
    c.execute('\n        UPDATE chat_aliases\n        SET alias = ?\n        WHERE alias = ? AND created_by = ?\n        ', (new_alias, existing_old_alias, created_by))
    conn.commit()
    conn.close()
    return True


def rename_user_alias_impl(old_alias: str, new_alias: str, created_by: int, *, deps) -> bool:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    existing_old_alias = _find_existing_alias_casefold(c, 'user_aliases', old_alias, created_by)
    if existing_old_alias is None:
        conn.close()
        return False
    if old_alias.casefold() != new_alias.casefold():
        if _find_existing_alias_casefold(c, 'user_aliases', new_alias, created_by) is not None:
            conn.close()
            raise ValueError(f"User-alias '{new_alias}' уже существует")
    c.execute('\n        UPDATE user_aliases\n        SET alias = ?\n        WHERE alias = ? AND created_by = ?\n        ', (new_alias, existing_old_alias, created_by))
    conn.commit()
    conn.close()
    return True


def get_private_chat_id_by_username_impl(username: str, *, deps) -> Optional[int]:
    _apply_deps(deps)
    if not username:
        return None
    u = username.strip()
    if u.startswith('@'):
        u = u[1:]
    if not u:
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute('\n            SELECT chat_id\n            FROM user_chats\n            WHERE LOWER(username) = LOWER(?)\n            ORDER BY updated_at DESC\n            LIMIT 1\n            ', (u,))
        row = c.fetchone()
        return int(row['chat_id']) if row else None
    finally:
        conn.close()


def set_chat_alias_for_user_impl(alias: str, chat_id: int, title: Optional[str], created_by: int, *, deps) -> None:
    _apply_deps(deps)
    try:
        set_chat_alias_impl(alias=alias, chat_id=chat_id, title=title, created_by=created_by, deps=deps)
    except TypeError as original_error:
        try:
            set_chat_alias_impl(alias=alias, chat_id=chat_id, title=title, deps=deps)
        except TypeError:
            raise original_error
