import os
import sqlite3


def _table_names(con):
    rows = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def _index_names(con, table: str):
    rows = con.execute(f"PRAGMA index_list({table})").fetchall()
    return {r[1] for r in rows}


def test_db_schema_has_expected_tables_and_index(main_module):
    con = sqlite3.connect(os.environ["DB_PATH"])
    try:
        tables = _table_names(con)

        assert "reminders" in tables
        assert "recurring_templates" in tables
        assert "user_chats" in tables
        assert "chat_aliases" in tables

        idxs = _index_names(con, "user_chats")
        assert "idx_user_chats_username" in idxs
    finally:
        con.close()