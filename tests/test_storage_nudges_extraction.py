import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

import dkreminders_bot.storage.storage_nudges as storage_nudges


TARGETS = [
    "_nudge_threshold_minutes",
    "get_due_nudges",
    "increment_nudge_count",
    "exhaust_nudges",
]


def _deps(db_path):
    return SimpleNamespace(
        DB_PATH=str(db_path),
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
            nudge_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )


def test_storage_nudges_wrappers_in_main_are_thin():
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
        if name != "_nudge_threshold_minutes":
            assert "deps=_build_storage_nudges_deps()" in node_source
        assert node.end_lineno - node.lineno + 1 <= 2


def test_storage_nudges_module_contains_impls_and_no_main_import():
    source = open("dkreminders_bot/storage/storage_nudges.py").read()

    for name in TARGETS:
        assert f"def {name}_impl(" in source

    assert "import main" not in source
    assert "from main import" not in source


def test_storage_nudges_thresholds():
    assert storage_nudges._nudge_threshold_minutes_impl(0) == 20
    assert storage_nudges._nudge_threshold_minutes_impl(1) == 80
    assert storage_nudges._nudge_threshold_minutes_impl(2) == 320
    assert storage_nudges._nudge_threshold_minutes_impl(3) == 1040
    assert storage_nudges._nudge_threshold_minutes_impl(4) is None
    assert storage_nudges._nudge_threshold_minutes_impl(-1) is None


def test_storage_nudges_due_filtering_and_marks(tmp_path):
    db_path = tmp_path / "nudges.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    rows = [
        (10, "due0", "2026-01-01T09:00:00+00:00", 1, 0),
        (10, "not-yet", "2026-01-01T09:50:00+00:00", 1, 0),
        (10, "acked", "2026-01-01T09:00:00+00:00", 1, 1),
        (10, "not-delivered", "2026-01-01T09:00:00+00:00", 0, 0),
        (10, "exhausted", "2026-01-01T09:00:00+00:00", 1, 0),
    ]
    for chat_id, text, sent_at, delivered, acked in rows:
        nudge_count = 4 if text == "exhausted" else 0
        conn.execute(
            """
            INSERT INTO reminders(chat_id, text, remind_at, created_by, created_at, delivered, acked, sent_at, nudge_count)
            VALUES (?, ?, '2026-01-01T08:00:00+00:00', 77, '2026-01-01T07:00:00+00:00', ?, ?, ?, ?)
            """,
            (chat_id, text, delivered, acked, sent_at, nudge_count),
        )
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    due = storage_nudges.get_due_nudges_impl(
        datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc),
        deps=deps,
    )

    assert [row["text"] for row in due] == ["due0"]

    rid = due[0]["id"]
    storage_nudges.increment_nudge_count_impl(rid, deps=deps)

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT nudge_count FROM reminders WHERE id = ?", (rid,)).fetchone()[0] == 1
    conn.close()

    storage_nudges.exhaust_nudges_impl(rid, deps=deps)

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT nudge_count FROM reminders WHERE id = ?", (rid,)).fetchone()[0] == 4
    conn.close()


def test_storage_nudges_skips_bad_sent_at(tmp_path):
    db_path = tmp_path / "nudges.db"
    conn = sqlite3.connect(db_path)
    _create_reminders_table(conn)
    conn.execute(
        """
        INSERT INTO reminders(chat_id, text, remind_at, created_by, created_at, delivered, acked, sent_at, nudge_count)
        VALUES (10, 'bad-date', '2026-01-01T08:00:00+00:00', 77, '2026-01-01T07:00:00+00:00', 1, 0, 'not-a-date', 0)
        """
    )
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    due = storage_nudges.get_due_nudges_impl(
        datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc),
        deps=deps,
    )

    assert due == []
