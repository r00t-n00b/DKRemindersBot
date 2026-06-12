import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


def _db_rows_by_id(reminder_id: int):
    db_path = os.environ["DB_PATH"]
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        tables = [r["name"] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]

        if "reminders" not in tables:
            raise AssertionError(f"Table 'reminders' not found. Tables: {tables}")

        return con.execute(
            "SELECT * FROM reminders WHERE id = ?",
            (reminder_id,),
        ).fetchall()
    finally:
        con.close()


def _db_rows_by_template(template_id: int):
    db_path = os.environ["DB_PATH"]
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        tables = [r["name"] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]

        if "reminders" not in tables:
            raise AssertionError(f"Table 'reminders' not found. Tables: {tables}")

        return con.execute(
            "SELECT * FROM reminders WHERE template_id = ?",
            (template_id,),
        ).fetchall()
    finally:
        con.close()


def test_add_list_delete_reminder(main_module):
    rid = main_module.add_reminder(
        chat_id=1,
        text="hi",
        remind_at=datetime.now(TZ),
        created_by=1,
    )
    assert isinstance(rid, int)

    rows = _db_rows_by_id(rid)
    assert len(rows) == 1
    assert rows[0]["id"] == rid

    db_path = os.environ["DB_PATH"]
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "DELETE FROM reminders WHERE id = ?",
            (rid,),
        )
        con.commit()
    finally:
        con.close()

    rows2 = _db_rows_by_id(rid)
    assert rows2 == []


def test_delete_recurring_template_cascades(main_module):
    tpl_id = main_module.create_recurring_template(
        chat_id=1,
        text="hi",
        pattern_type="daily",
        payload=None,
        time_hour=10,
        time_minute=0,
        created_by=1,
    )
    assert isinstance(tpl_id, int)

    rid = main_module.add_reminder(
        chat_id=1,
        text="hi",
        remind_at=datetime.now(TZ),
        created_by=1,
        template_id=tpl_id,
    )
    assert isinstance(rid, int)

    # В твоем main.py сигнатура требует chat_id
    main_module.delete_recurring_series(template_id=tpl_id, chat_id=1)

    rows = _db_rows_by_template(tpl_id)
    assert rows == []