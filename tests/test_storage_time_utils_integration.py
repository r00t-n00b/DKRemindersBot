import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import dkreminders_bot.storage.storage_write as storage_write


TZ = ZoneInfo("Europe/Madrid")


def _deps(db_path, now=None):
    return SimpleNamespace(
        DB_PATH=str(db_path),
        TZ=TZ,
        get_now=lambda: now or datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        json=__import__("json"),
        sqlite3=sqlite3,
    )


def _create_reminders_table(conn):
    conn.execute(
        """
        CREATE TABLE reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            remind_at TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            delivered INTEGER NOT NULL DEFAULT 0,
            template_id INTEGER,
            acked INTEGER NOT NULL DEFAULT 0,
            sent_at TEXT,
            nudge_count INTEGER NOT NULL DEFAULT 0,
            nudge_sent INTEGER NOT NULL DEFAULT 0,
            delivery_state TEXT NOT NULL DEFAULT 'pending',
            processing_started_at TEXT,
            delivery_attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            next_retry_at TEXT
        )
        """
    )


def _insert_due_reminder(conn, remind_at):
    cur = conn.execute(
        """
        INSERT INTO reminders(
            chat_id,
            text,
            remind_at,
            created_by,
            created_at,
            delivered,
            delivery_state,
            delivery_attempts
        )
        VALUES (100, 'hello', ?, 77, '2026-01-01T09:00:00+00:00', 0, 'pending', 0)
        """,
        (remind_at,),
    )
    return int(cur.lastrowid)


def _fetch_row(db_path, reminder_id):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def test_add_reminder_rejects_naive_remind_at(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="naive datetime"):
        storage_write.add_reminder_impl(
            100,
            "hello",
            datetime(2026, 1, 2, 10, 0),
            77,
            deps=_deps(db_path),
        )


def test_update_reminder_time_rejects_naive_datetime(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    reminder_id = _insert_due_reminder(conn, "2026-01-01T10:00:00+00:00")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="naive datetime"):
        storage_write.update_reminder_time_impl(
            reminder_id,
            datetime(2026, 1, 2, 10, 0),
            deps=_deps(db_path),
        )


def test_mark_reminder_sent_rejects_naive_sent_at(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    reminder_id = _insert_due_reminder(conn, "2026-01-01T10:00:00+00:00")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="naive datetime"):
        storage_write.mark_reminder_sent_impl(
            reminder_id,
            datetime(2026, 1, 2, 10, 0),
            deps=_deps(db_path),
        )


def test_mark_reminder_sent_rejects_naive_sent_at_string(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    reminder_id = _insert_due_reminder(conn, "2026-01-01T10:00:00+00:00")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="naive datetime"):
        storage_write.mark_reminder_sent_impl(
            reminder_id,
            "2026-01-02T10:00:00",
            deps=_deps(db_path),
        )


def test_claim_due_reminders_rejects_naive_now(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    _insert_due_reminder(conn, "2026-01-01T10:00:00+00:00")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="naive datetime"):
        storage_write.claim_due_reminders_impl(
            datetime(2026, 1, 2, 10, 0),
            deps=_deps(db_path),
        )


def test_mark_delivery_failed_rejects_naive_failed_at(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    reminder_id = _insert_due_reminder(conn, "2026-01-01T10:00:00+00:00")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="naive datetime"):
        storage_write.mark_reminder_delivery_failed_impl(
            reminder_id,
            "failed",
            failed_at=datetime(2026, 1, 2, 10, 0),
            deps=_deps(db_path),
        )


def test_reset_stale_processing_rejects_naive_now(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    reminder_id = _insert_due_reminder(conn, "2026-01-01T10:00:00+00:00")
    conn.execute(
        """
        UPDATE reminders
        SET delivery_state = 'processing',
            processing_started_at = '2026-01-01T10:00:00+00:00'
        WHERE id = ?
        """,
        (reminder_id,),
    )
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="naive datetime"):
        storage_write.reset_stale_processing_reminders_impl(
            datetime(2026, 1, 2, 10, 0),
            deps=_deps(db_path),
        )


def test_storage_write_keeps_aware_iso_values(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    conn.commit()
    conn.close()

    remind_at = datetime(2026, 1, 2, 10, 0, tzinfo=TZ)

    reminder_id = storage_write.add_reminder_impl(
        100,
        "hello",
        remind_at,
        77,
        deps=_deps(db_path),
    )

    row = _fetch_row(db_path, reminder_id)

    assert row["remind_at"] == "2026-01-02T10:00:00+01:00"
    assert row["delivery_state"] == "pending"
    assert row["delivery_attempts"] == 0


def test_mark_delivery_failed_sets_aware_retry_at(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    reminder_id = _insert_due_reminder(conn, "2026-01-01T10:00:00+00:00")
    conn.commit()
    conn.close()

    failed_at = datetime(2026, 1, 2, 10, 0, tzinfo=TZ)

    storage_write.mark_reminder_delivery_failed_impl(
        reminder_id,
        "telegram failed",
        failed_at=failed_at,
        retry_after_seconds=120,
        deps=_deps(db_path),
    )

    row = _fetch_row(db_path, reminder_id)

    assert row["delivery_state"] == "pending"
    assert row["next_retry_at"] == "2026-01-02T10:02:00+01:00"
    assert row["last_error"] == "telegram failed"


def test_reset_stale_processing_sets_aware_retry_at(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    reminder_id = _insert_due_reminder(conn, "2026-01-01T10:00:00+00:00")
    conn.execute(
        """
        UPDATE reminders
        SET delivery_state = 'processing',
            processing_started_at = '2026-01-02T09:00:00+01:00'
        WHERE id = ?
        """,
        (reminder_id,),
    )
    conn.commit()
    conn.close()

    now = datetime(2026, 1, 2, 10, 0, tzinfo=TZ)

    changed = storage_write.reset_stale_processing_reminders_impl(
        now,
        deps=_deps(db_path),
    )

    row = _fetch_row(db_path, reminder_id)

    assert changed == 1
    assert row["delivery_state"] == "pending"
    assert row["next_retry_at"] == "2026-01-02T10:00:00+01:00"
