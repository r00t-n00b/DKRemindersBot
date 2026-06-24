import sqlite3
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import storage_user_chats


TARGETS = [
    "upsert_user_chat",
    "get_user_chat_id_by_username",
    "get_user_chat_id_by_user_id",
]


def _deps(db_path):
    return SimpleNamespace(
        DB_PATH=str(db_path),
        TZ=ZoneInfo("Europe/Madrid"),
        sqlite3=sqlite3,
    )


def _create_user_chats_table(conn):
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


def test_storage_user_chats_wrappers_in_main_are_thin():
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
        assert "deps=_build_storage_user_chats_deps()" in node_source
        assert node.end_lineno - node.lineno + 1 <= 2


def test_storage_user_chats_module_contains_impls_and_no_main_import():
    source = open("storage_user_chats.py").read()

    for name in TARGETS:
        assert f"def {name}_impl(" in source

    assert "import main" not in source
    assert "from main import" not in source


def test_storage_user_chats_upsert_and_lookup(tmp_path):
    db_path = tmp_path / "user_chats.db"
    conn = sqlite3.connect(db_path)
    _create_user_chats_table(conn)
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    storage_user_chats.upsert_user_chat_impl(
        101,
        555,
        "MiXeDCase",
        "First",
        "Last",
        deps=deps,
    )

    assert storage_user_chats.get_user_chat_id_by_username_impl("@mixedcase", deps=deps) == 555
    assert storage_user_chats.get_user_chat_id_by_username_impl("MIXEDCASE", deps=deps) == 555
    assert storage_user_chats.get_user_chat_id_by_user_id_impl(101, deps=deps) == 555

    storage_user_chats.upsert_user_chat_impl(
        101,
        777,
        "NewName",
        "New",
        "User",
        deps=deps,
    )

    assert storage_user_chats.get_user_chat_id_by_username_impl("newname", deps=deps) == 777
    assert storage_user_chats.get_user_chat_id_by_user_id_impl(101, deps=deps) == 777
    assert storage_user_chats.get_user_chat_id_by_username_impl("", deps=deps) is None
    assert storage_user_chats.get_user_chat_id_by_username_impl("@missing", deps=deps) is None
    assert storage_user_chats.get_user_chat_id_by_user_id_impl(999, deps=deps) is None


def test_storage_user_chats_upsert_without_username(tmp_path):
    db_path = tmp_path / "user_chats.db"
    conn = sqlite3.connect(db_path)
    _create_user_chats_table(conn)
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    storage_user_chats.upsert_user_chat_impl(
        202,
        888,
        None,
        "No",
        "Username",
        deps=deps,
    )

    assert storage_user_chats.get_user_chat_id_by_user_id_impl(202, deps=deps) == 888
    assert storage_user_chats.get_user_chat_id_by_username_impl("", deps=deps) is None
