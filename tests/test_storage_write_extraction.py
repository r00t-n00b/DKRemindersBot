import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import dkreminders_bot.storage.storage_write as storage_write


TARGETS = [
    "add_reminder",
    "update_reminder_time",
    "mark_reminder_sent",
    "mark_reminder_acked",
    "mark_nudge_sent",
    "create_recurring_template",
]


def _deps(db_path):
    return SimpleNamespace(
        DB_PATH=str(db_path),
        TZ=ZoneInfo("Europe/Madrid"),
        get_now=lambda: datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
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
            nudge_sent INTEGER NOT NULL DEFAULT 0
        )
        """
    )


def _create_recurring_templates_table(conn):
    conn.execute(
        """
        CREATE TABLE recurring_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            pattern_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            time_hour INTEGER NOT NULL,
            time_minute INTEGER NOT NULL,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )


def test_storage_write_wrappers_in_main_are_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    for name in TARGETS:
        matches = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]

        assert len(matches) == 1

        node = matches[0]
        node_source = ast.get_source_segment(source, node)

        assert f"{name}_impl(" in node_source
        assert "deps=_build_storage_write_deps()" in node_source
        assert node.end_lineno - node.lineno + 1 <= 2


def test_storage_write_module_contains_impls_and_no_main_import_or_delete_logic():
    source = open("dkreminders_bot/storage/storage_write.py").read()

    for name in TARGETS:
        assert f"def {name}_impl(" in source

    assert "import main" not in source
    assert "from main import" not in source
    assert "DELETE FROM" not in source
    assert "restore_deleted_snapshot" not in source
    assert "delete_recurring" not in source


def test_storage_write_add_and_update_reminder(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    rid = storage_write.add_reminder_impl(
        10,
        "hello",
        datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        77,
        123,
        deps=deps,
    )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM reminders WHERE id = ?", (rid,)).fetchone()
    conn.close()

    assert row["chat_id"] == 10
    assert row["text"] == "hello"
    assert row["created_by"] == 77
    assert row["template_id"] == 123
    assert row["delivered"] == 0

    changed = storage_write.update_reminder_time_impl(
        rid,
        datetime(2026, 1, 6, 11, 0, tzinfo=timezone.utc),
        deps=deps,
    )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM reminders WHERE id = ?", (rid,)).fetchone()
    conn.close()

    assert changed is True
    assert row["remind_at"] == "2026-01-06T11:00:00+00:00"
    assert row["delivered"] == 0
    assert row["acked"] == 0
    assert row["sent_at"] is None
    assert row["nudge_count"] == 0


def test_storage_write_mark_helpers(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    conn.execute(
        """
        INSERT INTO reminders(chat_id, text, remind_at, created_by, created_at, delivered, acked, nudge_sent)
        VALUES (10, 'hello', '2026-01-01T10:00:00+00:00', 77, '2026-01-01T09:00:00+00:00', 0, 0, 0)
        """
    )
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    storage_write.mark_reminder_sent_impl(1, None, deps=deps)
    storage_write.mark_reminder_acked_impl(1, deps=deps)
    storage_write.mark_nudge_sent_impl(1, deps=deps)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM reminders WHERE id = 1").fetchone()
    conn.close()

    assert row["delivered"] == 1
    assert row["acked"] == 1
    assert row["nudge_sent"] == 1
    assert row["sent_at"] == "2026-01-02T03:04:00+00:00"


def test_storage_write_create_recurring_template(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
    _create_recurring_templates_table(conn)
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    tpl_id = storage_write.create_recurring_template_impl(
        20,
        "weekly",
        "weekly",
        {"weekday": 1},
        10,
        15,
        88,
        deps=deps,
    )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM recurring_templates WHERE id = ?", (tpl_id,)).fetchone()
    conn.close()

    assert row["chat_id"] == 20
    assert row["text"] == "weekly"
    assert row["pattern_type"] == "weekly"
    assert row["payload"] == '{"weekday": 1}'
    assert row["time_hour"] == 10
    assert row["time_minute"] == 15
    assert row["created_by"] == 88
    assert row["active"] == 1
