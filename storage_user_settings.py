"""Storage helpers for per-user settings."""

from datetime import datetime
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from time_utils import BOT_TZ, from_iso, to_iso


DEFAULT_TIMEZONE_NAME = "Europe/Madrid"

_DEP_NAMES = (
    "DB_PATH",
    "get_now",
    "sqlite3",
)


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def get_user_default_time_impl(user_id: Optional[int], *, deps) -> Optional[Tuple[int, int]]:
    _apply_deps(deps)
    if user_id is None:
        return None
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT default_hour, default_minute
            FROM user_settings
            WHERE user_id = ?
            """,
            (int(user_id),),
        ).fetchone()
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
        conn.execute(
            """
            INSERT INTO user_settings(user_id, default_hour, default_minute, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                default_hour = excluded.default_hour,
                default_minute = excluded.default_minute,
                updated_at = excluded.updated_at
            """,
            (int(user_id), int(hour), int(minute), get_now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def clear_user_default_time_impl(user_id: int, *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO user_settings(user_id, default_hour, default_minute, updated_at)
            VALUES (?, NULL, NULL, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                default_hour = NULL,
                default_minute = NULL,
                updated_at = excluded.updated_at
            """,
            (int(user_id), get_now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_timezone_name_impl(user_id: Optional[int], *, deps) -> Optional[str]:
    _apply_deps(deps)
    if user_id is None:
        return None

    conn = sqlite3.connect(DB_PATH)
    try:
        cols = _table_columns(conn, "user_settings")
        if "timezone_name" not in cols:
            return None

        row = conn.execute(
            """
            SELECT timezone_name
            FROM user_settings
            WHERE user_id = ?
            """,
            (int(user_id),),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    value = row[0]
    if not value:
        return None

    try:
        ZoneInfo(str(value))
        return str(value)
    except Exception:
        return None


def set_user_timezone_name_impl(user_id: int, timezone_name: str, *, deps) -> None:
    _apply_deps(deps)
    ZoneInfo(str(timezone_name))

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO user_settings(user_id, timezone_name, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                timezone_name = excluded.timezone_name,
                updated_at = excluded.updated_at
            """,
            (int(user_id), str(timezone_name), get_now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def count_active_reminders_for_user_impl(user_id: int, *, deps) -> int:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM reminders
            WHERE delivered = 0
              AND created_by = ?
            """,
            (int(user_id),),
        ).fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()


def count_active_recurring_templates_for_user_impl(user_id: int, *, deps) -> int:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM recurring_templates
            WHERE active = 1
              AND created_by = ?
            """,
            (int(user_id),),
        ).fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()


def _convert_preserving_local_time(remind_at_iso: str, old_tz: str, new_tz: str) -> str:
    old_zone = ZoneInfo(old_tz or DEFAULT_TIMEZONE_NAME)
    new_zone = ZoneInfo(new_tz or DEFAULT_TIMEZONE_NAME)

    dt = from_iso(remind_at_iso).astimezone(old_zone)
    moved = datetime(
        dt.year,
        dt.month,
        dt.day,
        dt.hour,
        dt.minute,
        dt.second,
        dt.microsecond,
        tzinfo=new_zone,
    )
    return to_iso(moved)


def move_active_reminders_timezone_for_user_impl(
    *,
    user_id: int,
    old_tz: str,
    new_tz: str,
    mode: str,
    deps,
) -> dict:
    _apply_deps(deps)
    if mode not in {"all", "oneoff", "recurring"}:
        raise ValueError(f"Unknown timezone migration mode: {mode}")

    ZoneInfo(old_tz or DEFAULT_TIMEZONE_NAME)
    ZoneInfo(new_tz or DEFAULT_TIMEZONE_NAME)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    reminders_changed = 0
    templates_changed = 0

    try:
        reminder_cols = _table_columns(conn, "reminders")
        template_cols = _table_columns(conn, "recurring_templates")

        if "timezone_name" not in reminder_cols:
            return {"reminders": 0, "templates": 0}

        conditions = ["delivered = 0", "created_by = ?"]
        params = [int(user_id)]

        if mode == "oneoff":
            conditions.append("template_id IS NULL")
        elif mode == "recurring":
            conditions.append("template_id IS NOT NULL")

        where_sql = " AND ".join(conditions)
        rows = conn.execute(
            f"""
            SELECT id, remind_at
            FROM reminders
            WHERE {where_sql}
            """,
            params,
        ).fetchall()

        for row in rows:
            new_iso = _convert_preserving_local_time(row["remind_at"], old_tz, new_tz)
            conn.execute(
                """
                UPDATE reminders
                SET remind_at = ?, timezone_name = ?
                WHERE id = ?
                """,
                (new_iso, new_tz, int(row["id"])),
            )
            reminders_changed += 1

        if mode in {"all", "recurring"} and "timezone_name" in template_cols:
            cur = conn.execute(
                """
                UPDATE recurring_templates
                SET timezone_name = ?
                WHERE active = 1
                  AND created_by = ?
                """,
                (new_tz, int(user_id)),
            )
            templates_changed = int(cur.rowcount or 0)

        conn.commit()
        return {"reminders": reminders_changed, "templates": templates_changed}
    finally:
        conn.close()
