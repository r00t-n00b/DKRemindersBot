import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import dkreminders_bot.storage.storage_delete_restore as storage_delete_restore
import dkreminders_bot.storage.storage_read as storage_read
import dkreminders_bot.storage.storage_write as storage_write


TARGETS = [
    "delete_reminders",
    "delete_recurring_one_instance_and_reschedule",
    "delete_single_reminder_row",
    "deactivate_recurring_template",
    "activate_recurring_template",
    "delete_recurring_series",
    "delete_reminder_with_snapshot",
    "delete_single_reminder_with_snapshot",
    "delete_recurring_series_with_snapshot",
    "restore_deleted_snapshot",
]


def _create_tables(conn):
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


def _deps(db_path):
    deps = SimpleNamespace()
    deps.DB_PATH = str(db_path)
    deps.sqlite3 = sqlite3

    read_deps = SimpleNamespace(DB_PATH=str(db_path), json=__import__("json"), sqlite3=sqlite3)
    write_deps = SimpleNamespace(
        DB_PATH=str(db_path),
        TZ=timezone.utc,
        get_now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        json=__import__("json"),
        sqlite3=sqlite3,
    )

    deps.get_reminder_row = lambda rid: storage_read.get_reminder_row_impl(rid, deps=read_deps)
    deps.get_recurring_template_row = lambda tpl_id: storage_read.get_recurring_template_row_impl(tpl_id, deps=read_deps)
    deps.get_reminders_by_template_id = lambda template_id, chat_id: storage_read.get_reminders_by_template_id_impl(template_id, chat_id, deps=read_deps)
    deps.add_reminder = lambda chat_id, text, remind_at, created_by, template_id=None: storage_write.add_reminder_impl(
        chat_id,
        text,
        remind_at,
        created_by,
        template_id,
        deps=write_deps,
    )
    deps.compute_next_occurrence = lambda pattern_type, payload, time_hour, time_minute, last_dt: last_dt + timedelta(days=1)

    return deps


def _insert_template(conn, *, chat_id=10, active=1):
    cur = conn.execute(
        """
        INSERT INTO recurring_templates(chat_id, text, pattern_type, payload, time_hour, time_minute, created_by, created_at, active)
        VALUES (?, 'tpl', 'daily', '{}', 10, 0, 77, '2026-01-01T09:00:00+00:00', ?)
        """,
        (chat_id, active),
    )
    return int(cur.lastrowid)


def _insert_reminder(conn, *, chat_id=10, text="hello", template_id=None, delivered=0):
    cur = conn.execute(
        """
        INSERT INTO reminders(chat_id, text, remind_at, created_by, created_at, delivered, template_id)
        VALUES (?, ?, '2026-01-02T10:00:00+00:00', 77, '2026-01-01T09:00:00+00:00', ?, ?)
        """,
        (chat_id, text, delivered, template_id),
    )
    return int(cur.lastrowid)


def test_storage_delete_restore_wrappers_in_main_are_thin():
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
        assert "deps=_build_storage_delete_restore_deps()" in node_source
        assert node.end_lineno - node.lineno + 1 <= 2


def test_storage_delete_restore_module_contains_impls_and_no_main_import():
    source = open("dkreminders_bot/storage/storage_delete_restore.py").read()

    for name in TARGETS:
        assert f"def {name}_impl(" in source

    assert "import main" not in source
    assert "from main import" not in source


def test_storage_delete_restore_single_delete_and_restore(tmp_path):
    db_path = tmp_path / "delete_restore.db"
    conn = sqlite3.connect(db_path)
    _create_tables(conn)
    rid = _insert_reminder(conn)
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    snapshot = storage_delete_restore.delete_single_reminder_with_snapshot_impl(
        rid,
        10,
        deps=deps,
    )

    assert snapshot["kind"] == "single"
    assert snapshot["reminder"]["text"] == "hello"

    conn = sqlite3.connect(db_path)
    remaining = conn.execute("SELECT COUNT(*) FROM reminders WHERE id = ?", (rid,)).fetchone()[0]
    conn.close()
    assert remaining == 0

    restored_id = storage_delete_restore.restore_deleted_snapshot_impl(snapshot, deps=deps)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT text, chat_id FROM reminders WHERE id = ?", (restored_id,)).fetchone()
    conn.close()

    assert row == ("hello", 10)


def test_storage_delete_restore_series_delete_and_restore(tmp_path):
    db_path = tmp_path / "delete_restore.db"
    conn = sqlite3.connect(db_path)
    _create_tables(conn)
    tpl_id = _insert_template(conn)
    _insert_reminder(conn, text="a", template_id=tpl_id)
    _insert_reminder(conn, text="b", template_id=tpl_id)
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    snapshot = storage_delete_restore.delete_recurring_series_with_snapshot_impl(
        tpl_id,
        10,
        deps=deps,
    )

    assert snapshot["kind"] == "series"
    assert len(snapshot["reminders"]) == 2

    conn = sqlite3.connect(db_path)
    reminders_left = conn.execute("SELECT COUNT(*) FROM reminders WHERE template_id = ?", (tpl_id,)).fetchone()[0]
    active = conn.execute("SELECT active FROM recurring_templates WHERE id = ?", (tpl_id,)).fetchone()[0]
    conn.close()

    assert reminders_left == 0
    assert active == 0

    restored_ids = storage_delete_restore.restore_deleted_snapshot_impl(snapshot, deps=deps)

    conn = sqlite3.connect(db_path)
    reminders_restored = conn.execute("SELECT COUNT(*) FROM reminders WHERE template_id = ?", (tpl_id,)).fetchone()[0]
    active = conn.execute("SELECT active FROM recurring_templates WHERE id = ?", (tpl_id,)).fetchone()[0]
    conn.close()

    assert len(restored_ids) == 2
    assert reminders_restored == 2
    assert active == 1


def test_storage_delete_restore_one_recurring_instance_reschedules_next(tmp_path):
    db_path = tmp_path / "delete_restore.db"
    conn = sqlite3.connect(db_path)
    _create_tables(conn)
    tpl_id = _insert_template(conn)
    rid = _insert_reminder(conn, template_id=tpl_id)
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    snapshot = storage_delete_restore.delete_recurring_one_instance_and_reschedule_impl(
        rid,
        10,
        deps=deps,
    )

    assert snapshot["kind"] == "single"
    assert snapshot["next_created_id"] is not None

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT id, text, template_id FROM reminders ORDER BY id").fetchall()
    active = conn.execute("SELECT active FROM recurring_templates WHERE id = ?", (tpl_id,)).fetchone()[0]
    conn.close()

    assert rows == [(snapshot["next_created_id"], "hello", tpl_id)]
    assert active == 1

    restored_id = storage_delete_restore.restore_deleted_snapshot_impl(snapshot, deps=deps)

    conn = sqlite3.connect(db_path)
    ids = [row[0] for row in conn.execute("SELECT id FROM reminders ORDER BY id").fetchall()]
    conn.close()

    assert ids == [restored_id]


def test_storage_delete_restore_delete_reminders_deactivates_templates(tmp_path):
    db_path = tmp_path / "delete_restore.db"
    conn = sqlite3.connect(db_path)
    _create_tables(conn)
    tpl_id = _insert_template(conn)
    rid = _insert_reminder(conn, template_id=tpl_id)
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    deleted = storage_delete_restore.delete_reminders_impl([rid], 10, deps=deps)

    conn = sqlite3.connect(db_path)
    reminders_left = conn.execute("SELECT COUNT(*) FROM reminders").fetchone()[0]
    active = conn.execute("SELECT active FROM recurring_templates WHERE id = ?", (tpl_id,)).fetchone()[0]
    conn.close()

    assert deleted == 1
    assert reminders_left == 0
    assert active == 0
