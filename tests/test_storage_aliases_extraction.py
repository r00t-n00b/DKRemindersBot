import sqlite3
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import dkreminders_bot.storage.storage_aliases as storage_aliases


TARGETS = [
    "set_chat_alias",
    "set_chat_alias_for_user",
    "get_chat_id_by_alias",
    "get_all_aliases",
    "get_user_alias",
    "set_user_alias",
    "get_user_alias_chat_id",
    "get_all_user_aliases",
    "delete_chat_alias",
    "delete_user_alias",
    "rename_chat_alias",
    "rename_user_alias",
    "get_private_chat_id_by_username",
]


def _deps(db_path):
    return SimpleNamespace(
        DB_PATH=str(db_path),
        TZ=ZoneInfo("Europe/Madrid"),
        sqlite3=sqlite3,
    )


def _create_alias_tables(conn):
    conn.execute(
        """
        CREATE TABLE chat_aliases (
            alias TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            title TEXT,
            created_by INTEGER NOT NULL,
            PRIMARY KEY (created_by, alias)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE user_aliases (
            alias TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            username TEXT,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (created_by, alias)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE user_chats (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )


def test_storage_aliases_wrappers_in_main_are_thin():
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

        if name == "set_chat_alias_for_user":
            assert "set_chat_alias(" in node_source
            assert "_set_chat_alias_accepts_created_by()" in node_source
            assert "set_chat_alias_for_user_impl" not in node_source
        else:
            assert f"{name}_impl(" in node_source
            assert "deps=_build_storage_aliases_deps()" in node_source

        assert node.end_lineno - node.lineno + 1 <= 2

    assert "_find_existing_alias_casefold" not in [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]


def test_storage_aliases_module_contains_impls_and_no_main_import():
    source = open("dkreminders_bot/storage/storage_aliases.py").read()

    assert "def _find_existing_alias_casefold(" in source

    for name in TARGETS:
        assert f"def {name}_impl(" in source

    assert "import main" not in source
    assert "from main import" not in source


def test_storage_aliases_chat_alias_crud_and_casefold(tmp_path):
    db_path = tmp_path / "aliases.db"
    conn = sqlite3.connect(db_path)
    _create_alias_tables(conn)
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    storage_aliases.set_chat_alias_impl("Home", 100, "Home Chat", 7, deps=deps)

    assert storage_aliases.get_chat_id_by_alias_impl("home", 7, deps=deps) == 100
    assert storage_aliases.get_chat_id_by_alias_impl("HOME", 7, deps=deps) == 100
    assert storage_aliases.get_chat_id_by_alias_impl("home", 8, deps=deps) is None

    storage_aliases.set_chat_alias_for_user_impl("Home", 101, "New Title", 7, deps=deps)

    assert storage_aliases.get_chat_id_by_alias_impl("home", 7, deps=deps) == 101

    aliases = storage_aliases.get_all_aliases_impl(7, deps=deps)
    assert aliases == [("Home", 101, "New Title")]

    assert storage_aliases.rename_chat_alias_impl("home", "Casa", 7, deps=deps) is True
    assert storage_aliases.get_chat_id_by_alias_impl("casa", 7, deps=deps) == 101

    assert storage_aliases.delete_chat_alias_impl("CASA", 7, deps=deps) is True
    assert storage_aliases.get_chat_id_by_alias_impl("casa", 7, deps=deps) is None
    assert storage_aliases.delete_chat_alias_impl("missing", 7, deps=deps) is False


def test_storage_aliases_user_alias_crud_and_casefold(tmp_path):
    db_path = tmp_path / "aliases.db"
    conn = sqlite3.connect(db_path)
    _create_alias_tables(conn)
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    storage_aliases.set_user_alias_impl("Natasha", 200, 300, "natasha", 7, deps=deps)

    row = storage_aliases.get_user_alias_impl("natasha", 7, deps=deps)

    assert row["alias"] == "Natasha"
    assert row["user_id"] == 200
    assert row["chat_id"] == 300
    assert row["username"] == "natasha"

    assert storage_aliases.get_user_alias_chat_id_impl("NATASHA", 7, deps=deps) == 300
    assert storage_aliases.get_all_user_aliases_impl(7, deps=deps) == [("Natasha", 300)]

    storage_aliases.set_user_alias_impl("NATASHA", 201, 301, "nat2", 7, deps=deps)
    row = storage_aliases.get_user_alias_impl("natasha", 7, deps=deps)

    assert row["alias"] == "Natasha"
    assert row["user_id"] == 201
    assert row["chat_id"] == 301
    assert row["username"] == "nat2"

    assert storage_aliases.rename_user_alias_impl("natasha", "Nata", 7, deps=deps) is True
    assert storage_aliases.get_user_alias_chat_id_impl("nata", 7, deps=deps) == 301

    assert storage_aliases.delete_user_alias_impl("NATA", 7, deps=deps) is True
    assert storage_aliases.get_user_alias_impl("nata", 7, deps=deps) is None
    assert storage_aliases.delete_user_alias_impl("missing", 7, deps=deps) is False


def test_storage_aliases_rename_conflict_raises(tmp_path):
    db_path = tmp_path / "aliases.db"
    conn = sqlite3.connect(db_path)
    _create_alias_tables(conn)
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    storage_aliases.set_chat_alias_impl("a", 1, "A", 7, deps=deps)
    storage_aliases.set_chat_alias_impl("b", 2, "B", 7, deps=deps)

    try:
        storage_aliases.rename_chat_alias_impl("a", "B", 7, deps=deps)
    except ValueError as e:
        assert "уже существует" in str(e)
    else:
        raise AssertionError("Expected ValueError")

    storage_aliases.set_user_alias_impl("u1", 1, 1, "u1", 7, deps=deps)
    storage_aliases.set_user_alias_impl("u2", 2, 2, "u2", 7, deps=deps)

    try:
        storage_aliases.rename_user_alias_impl("u1", "U2", 7, deps=deps)
    except ValueError as e:
        assert "уже существует" in str(e)
    else:
        raise AssertionError("Expected ValueError")


def test_storage_aliases_private_chat_lookup_by_username(tmp_path):
    db_path = tmp_path / "aliases.db"
    conn = sqlite3.connect(db_path)
    _create_alias_tables(conn)
    conn.execute(
        """
        INSERT INTO user_chats(user_id, chat_id, username, first_name, last_name, updated_at)
        VALUES (1, 500, 'friend', 'F', 'R', '2026-01-01T10:00:00')
        """
    )
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    assert storage_aliases.get_private_chat_id_by_username_impl("@friend", deps=deps) == 500
    assert storage_aliases.get_private_chat_id_by_username_impl("FRIEND", deps=deps) == 500
    assert storage_aliases.get_private_chat_id_by_username_impl("", deps=deps) is None
    assert storage_aliases.get_private_chat_id_by_username_impl("@missing", deps=deps) is None
