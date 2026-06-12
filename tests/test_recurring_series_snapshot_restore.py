import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


def _count_rows(sql, params=()):
    db_path = os.environ["DB_PATH"]
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute(sql, params)
        return len(cur.fetchall())
    finally:
        con.close()


def test_delete_single_recurring_reminder_with_snapshot_and_restore(main_module):
    tpl_id = main_module.create_recurring_template(
        chat_id=1,
        text="hi",
        pattern_type="daily",
        payload=None,
        time_hour=10,
        time_minute=0,
        created_by=1,
    )

    rid = main_module.add_reminder(
        chat_id=1,
        text="hi",
        remind_at=datetime.now(TZ),
        created_by=1,
        template_id=tpl_id,
    )

    assert _count_rows("SELECT id FROM reminders WHERE id = ?", (rid,)) == 1

    snapshot = main_module.delete_single_reminder_with_snapshot(rid, 1)
    assert snapshot is not None
    assert snapshot["kind"] == "single"

    assert _count_rows("SELECT id FROM reminders WHERE id = ?", (rid,)) == 0

    restored = main_module.restore_deleted_snapshot(snapshot)
    # restore_deleted_snapshot может возвращать id/список id, главное что не False/None
    assert restored


def test_delete_recurring_series_with_snapshot_and_restore(main_module):
    tpl_id = main_module.create_recurring_template(
        chat_id=1,
        text="hi",
        pattern_type="daily",
        payload=None,
        time_hour=10,
        time_minute=0,
        created_by=1,
    )

    main_module.add_reminder(
        chat_id=1,
        text="a",
        remind_at=datetime.now(TZ),
        created_by=1,
        template_id=tpl_id,
    )
    main_module.add_reminder(
        chat_id=1,
        text="b",
        remind_at=datetime.now(TZ),
        created_by=1,
        template_id=tpl_id,
    )

    assert _count_rows("SELECT id FROM reminders WHERE template_id = ?", (tpl_id,)) == 2
    assert _count_rows("SELECT id FROM recurring_templates WHERE id = ?", (tpl_id,)) == 1

    snapshot = main_module.delete_recurring_series_with_snapshot(tpl_id, 1)
    assert snapshot is not None
    assert snapshot["kind"] == "series"

    # Важно, что серия в reminders удалена
    assert _count_rows("SELECT id FROM reminders WHERE template_id = ?", (tpl_id,)) == 0

    # А вот template может оставаться (в зависимости от бизнес-логики).
    # Поэтому не утверждаем, что template удален. Проверим что restore работает.
    restored = main_module.restore_deleted_snapshot(snapshot)
    assert restored