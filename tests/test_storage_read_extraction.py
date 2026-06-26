import sqlite3
from datetime import datetime
from types import SimpleNamespace

import pytest

import main
import storage_read


TARGETS = [
    "get_due_reminders",
    "get_reminder",
    "get_active_reminders_created_by_for_chat",
    "get_active_reminders_for_chat",
    "get_reminder_row",
    "get_recurring_template_row",
    "get_reminders_by_template_id",
    "get_unacked_sent_before",
    "get_recurring_template",
]


def test_storage_read_wrappers_in_main_are_thin():
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
        assert "_build_storage_read_deps()" in node_source
        assert node.end_lineno - node.lineno + 1 <= 2


def test_storage_read_module_contains_impls_and_no_main_import():
    source = open("storage_read.py").read()

    for name in TARGETS:
        assert f"def {name}_impl(" in source

    assert "import main" not in source
    assert "from main import" not in source


def test_storage_read_get_due_reminders_returns_models(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
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
            nudge_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO reminders(chat_id, text, remind_at, created_by, created_at, delivered, template_id)
        VALUES (10, 'due', '2026-01-01T10:00:00+00:00', 7, '2026-01-01T09:00:00+00:00', 0, NULL)
        """
    )
    conn.execute(
        """
        INSERT INTO reminders(chat_id, text, remind_at, created_by, created_at, delivered, template_id)
        VALUES (10, 'future', '2026-01-03T10:00:00+00:00', 7, '2026-01-01T09:00:00+00:00', 0, NULL)
        """
    )
    conn.commit()
    conn.close()

    deps = SimpleNamespace(DB_PATH=str(db_path), json=__import__("json"), sqlite3=sqlite3)

    rows = storage_read.get_due_reminders_impl(
        datetime.fromisoformat("2026-01-02T10:00:00+00:00"),
        deps,
    )

    assert len(rows) == 1
    assert rows[0].text == "due"
    assert rows[0].chat_id == 10
    assert rows[0].created_by == 7
    assert rows[0].remind_at.isoformat() == "2026-01-01T10:00:00+00:00"


def test_storage_read_get_due_reminders_rejects_naive_now(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
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
            nudge_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()

    deps = SimpleNamespace(DB_PATH=str(db_path), json=__import__("json"), sqlite3=sqlite3)

    with pytest.raises(ValueError, match="naive datetime"):
        storage_read.get_due_reminders_impl(
            datetime.fromisoformat("2026-01-02T10:00:00"),
            deps,
        )


def test_storage_read_get_due_reminders_rejects_naive_remind_at_from_db(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
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
            nudge_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO reminders(chat_id, text, remind_at, created_by, created_at, delivered, template_id)
        VALUES (10, 'due', '2026-01-01T10:00:00', 7, '2026-01-01T09:00:00+00:00', 0, NULL)
        """
    )
    conn.commit()
    conn.close()

    deps = SimpleNamespace(DB_PATH=str(db_path), json=__import__("json"), sqlite3=sqlite3)

    with pytest.raises(ValueError, match="naive datetime"):
        storage_read.get_due_reminders_impl(
            datetime.fromisoformat("2026-01-02T10:00:00+00:00"),
            deps,
        )


def test_storage_read_get_reminder_uses_aware_timestamps(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
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
            nudge_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO reminders(chat_id, text, remind_at, created_by, created_at, delivered, template_id, sent_at)
        VALUES (
            10,
            'hello',
            '2026-01-01T10:00:00+00:00',
            7,
            '2026-01-01T09:00:00+00:00',
            1,
            NULL,
            '2026-01-01T10:01:00+00:00'
        )
        """
    )
    conn.commit()
    conn.close()

    deps = SimpleNamespace(DB_PATH=str(db_path), json=__import__("json"), sqlite3=sqlite3)

    reminder = storage_read.get_reminder_impl(1, deps)

    assert reminder.text == "hello"
    assert reminder.remind_at.isoformat() == "2026-01-01T10:00:00+00:00"
    assert reminder.sent_at.isoformat() == "2026-01-01T10:01:00+00:00"


def test_storage_read_get_reminder_rejects_naive_timestamps_from_db(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
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
            nudge_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO reminders(chat_id, text, remind_at, created_by, created_at, delivered, template_id, sent_at)
        VALUES (
            10,
            'hello',
            '2026-01-01T10:00:00',
            7,
            '2026-01-01T09:00:00+00:00',
            1,
            NULL,
            '2026-01-01T10:01:00+00:00'
        )
        """
    )
    conn.commit()
    conn.close()

    deps = SimpleNamespace(DB_PATH=str(db_path), json=__import__("json"), sqlite3=sqlite3)

    with pytest.raises(ValueError, match="naive datetime"):
        storage_read.get_reminder_impl(1, deps)


def test_storage_read_get_reminder_row_and_active_lists(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
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
            nudge_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        INSERT INTO reminders(chat_id, text, remind_at, created_by, created_at, delivered, template_id)
        VALUES (20, 'active', '2026-01-01T10:00:00+00:00', 77, '2026-01-01T09:00:00+00:00', 0, 5)
        """
    )
    conn.execute(
        """
        INSERT INTO reminders(chat_id, text, remind_at, created_by, created_at, delivered, template_id)
        VALUES (20, 'done', '2026-01-01T11:00:00+00:00', 77, '2026-01-01T09:00:00+00:00', 1, 5)
        """
    )
    conn.commit()
    conn.close()

    deps = SimpleNamespace(DB_PATH=str(db_path), json=__import__("json"), sqlite3=sqlite3)

    row = storage_read.get_reminder_row_impl(1, deps)
    assert row["text"] == "active"
    assert row["template_id"] == 5

    active = storage_read.get_active_reminders_for_chat_impl(20, deps)
    assert [r["text"] for r in active] == ["active"]

    active_by_creator = storage_read.get_active_reminders_created_by_for_chat_impl(20, 77, deps)
    assert [r["text"] for r in active_by_creator] == ["active"]


def test_storage_read_recurring_template_payload_json(tmp_path):
    db_path = tmp_path / "reminders.db"
    conn = sqlite3.connect(db_path)
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
    conn.execute(
        """
        INSERT INTO recurring_templates(chat_id, text, pattern_type, payload, time_hour, time_minute, created_by, created_at, active)
        VALUES (30, 'tpl', 'weekly', '{"weekday": 1}', 10, 15, 88, '2026-01-01T09:00:00', 1)
        """
    )
    conn.commit()
    conn.close()

    deps = SimpleNamespace(DB_PATH=str(db_path), json=__import__("json"), sqlite3=sqlite3)

    tpl = storage_read.get_recurring_template_impl(1, deps)
    assert tpl["payload"] == {"weekday": 1}
    assert tpl["active"] is True

    tpl_row = storage_read.get_recurring_template_row_impl(1, deps)
    assert tpl_row["payload"] == {"weekday": 1}
