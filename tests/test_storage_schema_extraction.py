import sqlite3
from types import SimpleNamespace

import dkreminders_bot.storage.storage_schema as storage_schema


TARGETS = [
    "_ensure_column",
    "init_db",
    "migrate_alias_tables_to_owner_scope",
]


class DummyLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(message)


def _deps(db_path):
    return SimpleNamespace(
        DB_PATH=str(db_path),
        logger=DummyLogger(),
        sqlite3=sqlite3,
    )


def _table_info(conn, table):
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _pk_cols(conn, table):
    rows = _table_info(conn, table)
    return [
        row["name"]
        for row in sorted([r for r in rows if r["pk"]], key=lambda r: r["pk"])
    ]


def test_storage_schema_wrappers_in_main_are_thin():
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
        assert "deps=_build_storage_schema_deps()" in node_source
        assert node.end_lineno - node.lineno + 1 <= 2


def test_storage_schema_module_contains_impls_and_no_main_import():
    source = open("dkreminders_bot/storage/storage_schema.py").read()

    assert "def _ensure_column_impl(" in source
    assert "def init_db_impl(" in source
    assert "def migrate_alias_tables_to_owner_scope_impl(" in source

    assert "CREATE TABLE IF NOT EXISTS reminders" in source
    assert "CREATE TABLE IF NOT EXISTS reminder_messages" in source
    assert "CREATE TABLE IF NOT EXISTS chat_aliases" in source
    assert "CREATE TABLE IF NOT EXISTS user_aliases" in source

    assert "import main" not in source
    assert "from main import" not in source


def test_storage_schema_init_db_creates_expected_tables_and_columns(tmp_path):
    db_path = tmp_path / "schema.db"
    deps = _deps(db_path)

    storage_schema.init_db_impl(deps=deps)

    conn = sqlite3.connect(db_path)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = ?",
            ("table",),
        ).fetchall()
    }

    assert "reminders" in tables
    assert "reminder_messages" in tables
    assert "chat_aliases" in tables
    assert "recurring_templates" in tables
    assert "user_aliases" in tables
    assert "user_chats" in tables
    assert "user_settings" in tables

    reminder_cols = {row["name"] for row in _table_info(conn, "reminders")}
    assert {
        "id",
        "chat_id",
        "text",
        "remind_at",
        "created_by",
        "created_at",
        "delivered",
        "template_id",
        "acked",
        "sent_at",
        "nudge_count",
    }.issubset(reminder_cols)

    assert _pk_cols(conn, "chat_aliases") == ["created_by", "alias"]
    assert _pk_cols(conn, "user_aliases") == ["created_by", "alias"]

    conn.close()


def test_storage_schema_init_db_migrates_old_reminders_columns(tmp_path):
    db_path = tmp_path / "schema.db"
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
            delivered INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    storage_schema.init_db_impl(deps=deps)

    conn = sqlite3.connect(db_path)
    cols = {row["name"] for row in _table_info(conn, "reminders")}
    conn.close()

    assert "template_id" in cols
    assert "acked" in cols
    assert "sent_at" in cols
    assert "nudge_count" in cols


def test_storage_schema_migrates_user_aliases_owner_scope(tmp_path):
    db_path = tmp_path / "schema.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE user_aliases (
            alias TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            username TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO user_aliases(alias, user_id, chat_id, username, created_by, created_at)
        VALUES ('Natasha', 1, 11, 'natasha', 777, '2026-01-01T10:00:00')
        """
    )
    conn.execute(
        """
        CREATE TABLE chat_aliases (
            alias TEXT PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            title TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO chat_aliases(alias, chat_id, title)
        VALUES ('oldchat', 99, 'Old Chat')
        """
    )
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    storage_schema.migrate_alias_tables_to_owner_scope_impl(deps=deps)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    assert _pk_cols(conn, "user_aliases") == ["created_by", "alias"]
    assert _pk_cols(conn, "chat_aliases") == ["created_by", "alias"]

    user_rows = [dict(row) for row in conn.execute("SELECT * FROM user_aliases").fetchall()]
    chat_rows = [dict(row) for row in conn.execute("SELECT * FROM chat_aliases").fetchall()]

    conn.close()

    assert user_rows == [
        {
            "alias": "Natasha",
            "user_id": 1,
            "chat_id": 11,
            "username": "natasha",
            "created_by": 777,
            "created_at": "2026-01-01T10:00:00",
        }
    ]

    # Старые chat_aliases без created_by намеренно не мигрируются.
    assert chat_rows == []


def test_storage_schema_migration_is_idempotent_on_current_schema(tmp_path):
    db_path = tmp_path / "schema.db"
    deps = _deps(db_path)

    storage_schema.init_db_impl(deps=deps)
    storage_schema.migrate_alias_tables_to_owner_scope_impl(deps=deps)
    storage_schema.migrate_alias_tables_to_owner_scope_impl(deps=deps)

    conn = sqlite3.connect(db_path)

    assert _pk_cols(conn, "user_aliases") == ["created_by", "alias"]
    assert _pk_cols(conn, "chat_aliases") == ["created_by", "alias"]

    conn.close()
