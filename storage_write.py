"""Write-only storage helpers for reminder creation/update/mark operations."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from models import Reminder
from time_utils import from_iso, to_iso


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


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def add_reminder_impl(
    chat_id: int,
    text: str,
    remind_at: datetime,
    created_by: Optional[int],
    template_id: Optional[int] = None,
    *,
    deps,
) -> int:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    try:
        cols = _table_columns(conn, "reminders")

        insert_cols = [
            "chat_id",
            "text",
            "remind_at",
            "created_by",
            "created_at",
            "delivered",
            "template_id",
        ]
        values = [
            chat_id,
            text,
            to_iso(remind_at),
            created_by,
            datetime.now(TZ).isoformat(),
            0,
            template_id,
        ]

        if "delivery_state" in cols:
            insert_cols.append("delivery_state")
            values.append("pending")
        if "delivery_attempts" in cols:
            insert_cols.append("delivery_attempts")
            values.append(0)

        placeholders = ", ".join("?" for _ in insert_cols)
        column_sql = ", ".join(insert_cols)

        c = conn.cursor()
        c.execute(
            f"""
            INSERT INTO reminders ({column_sql})
            VALUES ({placeholders})
            """,
            values,
        )
        reminder_id = c.lastrowid
        conn.commit()
        return reminder_id
    finally:
        conn.close()


def update_reminder_time_impl(reminder_id: int, new_dt: datetime, *, deps) -> bool:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    try:
        cols = _table_columns(conn, "reminders")

        assignments = [
            "remind_at = ?",
            "delivered = 0",
            "acked = 0",
            "sent_at = NULL",
            "nudge_count = 0",
        ]
        values = [to_iso(new_dt)]

        if "delivery_state" in cols:
            assignments.append("delivery_state = 'pending'")
        if "processing_started_at" in cols:
            assignments.append("processing_started_at = NULL")
        if "last_error" in cols:
            assignments.append("last_error = NULL")
        if "next_retry_at" in cols:
            assignments.append("next_retry_at = NULL")

        values.append(int(reminder_id))

        c = conn.cursor()
        c.execute(
            f"""
            UPDATE reminders
            SET {", ".join(assignments)}
            WHERE id = ?
            """,
            values,
        )
        changed = c.rowcount > 0
        conn.commit()
        return changed
    finally:
        conn.close()


def mark_reminder_sent_impl(
    reminder_id: int,
    sent_at: Optional[datetime] = None,
    *,
    deps,
) -> None:
    _apply_deps(deps)
    if sent_at is None:
        sent_at = get_now()
    if isinstance(sent_at, str):
        sent_at = from_iso(sent_at)

    conn = sqlite3.connect(DB_PATH)
    try:
        cols = _table_columns(conn, "reminders")

        assignments = [
            "delivered = 1",
            "sent_at = ?",
            "acked = 0",
        ]
        values = [to_iso(sent_at)]

        if "delivery_state" in cols:
            assignments.append("delivery_state = 'sent'")
        if "processing_started_at" in cols:
            assignments.append("processing_started_at = NULL")
        if "last_error" in cols:
            assignments.append("last_error = NULL")
        if "next_retry_at" in cols:
            assignments.append("next_retry_at = NULL")

        values.append(int(reminder_id))

        conn.execute(
            f"""
            UPDATE reminders
            SET {", ".join(assignments)}
            WHERE id = ?
            """,
            values,
        )
        conn.commit()
    finally:
        conn.close()


def claim_due_reminders_impl(
    now: datetime,
    *,
    deps,
    limit: int = 50,
) -> List[Reminder]:
    _apply_deps(deps)
    now_iso = to_iso(now)

    conn = sqlite3.connect(DB_PATH)
    try:
        cols = _table_columns(conn, "reminders")
        if "delivery_state" not in cols:
            c = conn.cursor()
            c.execute(
                """
                SELECT id, chat_id, text, remind_at, created_by, template_id
                FROM reminders
                WHERE delivered = 0 AND remind_at <= ?
                ORDER BY remind_at ASC
                LIMIT ?
                """,
                (now_iso, int(limit)),
            )
            rows = c.fetchall()
        else:
            conn.isolation_level = None
            conn.execute("BEGIN IMMEDIATE")
            c = conn.cursor()
            c.execute(
                """
                SELECT id, chat_id, text, remind_at, created_by, template_id
                FROM reminders
                WHERE delivered = 0
                  AND delivery_state = 'pending'
                  AND remind_at <= ?
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY remind_at ASC
                LIMIT ?
                """,
                (now_iso, now_iso, int(limit)),
            )
            rows = c.fetchall()
            ids = [int(row[0]) for row in rows]

            if ids:
                qmarks = ",".join("?" for _ in ids)
                c.execute(
                    f"""
                    UPDATE reminders
                    SET delivery_state = 'processing',
                        processing_started_at = ?,
                        delivery_attempts = COALESCE(delivery_attempts, 0) + 1
                    WHERE id IN ({qmarks})
                      AND delivered = 0
                      AND delivery_state = 'pending'
                    """,
                    [now_iso, *ids],
                )

            conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

    reminders: List[Reminder] = []
    for row in rows:
        rid, chat_id, text, remind_at_str, created_by, template_id = row
        reminders.append(
            Reminder(
                id=rid,
                chat_id=chat_id,
                text=text,
                remind_at=from_iso(remind_at_str),
                created_by=created_by,
                template_id=template_id,
            )
        )
    return reminders


def mark_reminder_delivery_failed_impl(
    reminder_id: int,
    error: str,
    *,
    deps,
    failed_at: Optional[datetime] = None,
    retry_after_seconds: int = 60,
) -> None:
    _apply_deps(deps)
    if failed_at is None:
        failed_at = get_now()
    retry_at = failed_at + timedelta(seconds=retry_after_seconds)
    safe_error = str(error or "")[:1000]

    conn = sqlite3.connect(DB_PATH)
    try:
        cols = _table_columns(conn, "reminders")
        if "delivery_state" not in cols:
            return

        conn.execute(
            """
            UPDATE reminders
            SET delivery_state = 'pending',
                processing_started_at = NULL,
                last_error = ?,
                next_retry_at = ?
            WHERE id = ?
              AND delivered = 0
            """,
            (safe_error, to_iso(retry_at), int(reminder_id)),
        )
        conn.commit()
    finally:
        conn.close()


def reset_stale_processing_reminders_impl(
    now: datetime,
    *,
    deps,
    stale_after_seconds: int = 600,
) -> int:
    _apply_deps(deps)
    cutoff = now - timedelta(seconds=stale_after_seconds)

    conn = sqlite3.connect(DB_PATH)
    try:
        cols = _table_columns(conn, "reminders")
        if "delivery_state" not in cols:
            return 0

        c = conn.cursor()
        c.execute(
            """
            UPDATE reminders
            SET delivery_state = 'pending',
                processing_started_at = NULL,
                last_error = 'Reset stale processing reminder',
                next_retry_at = ?
            WHERE delivered = 0
              AND delivery_state = 'processing'
              AND processing_started_at IS NOT NULL
              AND processing_started_at <= ?
            """,
            (to_iso(now), to_iso(cutoff)),
        )
        changed = c.rowcount
        conn.commit()
        return changed
    finally:
        conn.close()


def mark_reminder_acked_impl(reminder_id: int, *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reminders SET acked = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


def mark_nudge_sent_impl(reminder_id: int, *, deps) -> None:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reminders SET nudge_sent = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


def create_recurring_template_impl(
    chat_id: int,
    text: str,
    pattern_type: str,
    payload: Dict[str, Any],
    time_hour: int,
    time_minute: int,
    created_by: Optional[int],
    *,
    deps,
) -> int:
    _apply_deps(deps)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO recurring_templates
            (chat_id, text, pattern_type, payload, time_hour, time_minute, created_by, created_at, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            chat_id,
            text,
            pattern_type,
            json.dumps(payload, ensure_ascii=False),
            time_hour,
            time_minute,
            created_by,
            datetime.now(TZ).isoformat(),
        ),
    )
    tpl_id = c.lastrowid
    conn.commit()
    conn.close()
    return tpl_id
