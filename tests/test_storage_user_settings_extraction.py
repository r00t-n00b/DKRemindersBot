import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

import dkreminders_bot.storage.storage_user_settings as storage_user_settings


TARGETS = [
    "get_user_default_time",
    "set_user_default_time",
    "clear_user_default_time",
]


def _deps(db_path):
    return SimpleNamespace(
        DB_PATH=str(db_path),
        get_now=lambda: datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        sqlite3=sqlite3,
    )


def _create_user_settings_table(conn):
    conn.execute(
        """
        CREATE TABLE user_settings (
            user_id INTEGER PRIMARY KEY,
            default_hour INTEGER,
            default_minute INTEGER,
            updated_at TEXT
        )
        """
    )


def test_storage_user_settings_wrappers_in_main_are_thin():
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
        assert "deps=_build_storage_user_settings_deps()" in node_source
        assert node.end_lineno - node.lineno + 1 <= 2


def test_storage_user_settings_module_contains_impls_and_no_main_import():
    source = open("dkreminders_bot/storage/storage_user_settings.py").read()

    for name in TARGETS:
        assert f"def {name}_impl(" in source

    assert "import main" not in source
    assert "from main import" not in source


def test_storage_user_settings_get_set_clear_default_time(tmp_path):
    db_path = tmp_path / "settings.db"
    conn = sqlite3.connect(db_path)
    _create_user_settings_table(conn)
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    assert storage_user_settings.get_user_default_time_impl(None, deps=deps) is None
    assert storage_user_settings.get_user_default_time_impl(123, deps=deps) is None

    storage_user_settings.set_user_default_time_impl(123, 9, 45, deps=deps)

    assert storage_user_settings.get_user_default_time_impl(123, deps=deps) == (9, 45)

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT default_hour, default_minute, updated_at FROM user_settings WHERE user_id = 123"
    ).fetchone()
    conn.close()

    assert row[0] == 9
    assert row[1] == 45
    assert row[2] == "2026-01-02T03:04:00+00:00"

    storage_user_settings.set_user_default_time_impl(123, 10, 30, deps=deps)
    assert storage_user_settings.get_user_default_time_impl(123, deps=deps) == (10, 30)

    storage_user_settings.clear_user_default_time_impl(123, deps=deps)
    assert storage_user_settings.get_user_default_time_impl(123, deps=deps) is None


def test_storage_user_settings_invalid_row_returns_none(tmp_path):
    db_path = tmp_path / "settings.db"
    conn = sqlite3.connect(db_path)
    _create_user_settings_table(conn)
    conn.execute(
        "INSERT INTO user_settings(user_id, default_hour, default_minute, updated_at) VALUES (1, NULL, 30, 'x')"
    )
    conn.commit()
    conn.close()

    deps = _deps(db_path)

    assert storage_user_settings.get_user_default_time_impl(1, deps=deps) is None
