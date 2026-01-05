from datetime import timedelta


def test_add_get_due_mark(main_module, fixed_now):
    rid = main_module.add_reminder(
        chat_id=123,
        text="hi",
        remind_at=fixed_now - timedelta(minutes=1),
        created_by=1,
        template_id=None,
    )
    due = main_module.get_due_reminders(fixed_now)
    assert len(due) == 1
    assert due[0].id == rid

    main_module.mark_reminder_sent(rid)
    due2 = main_module.get_due_reminders(fixed_now)
    assert due2 == []


def test_get_reminder(main_module, fixed_now):
    rid = main_module.add_reminder(
        chat_id=123,
        text="hi",
        remind_at=fixed_now,
        created_by=1,
        template_id=None,
    )
    r = main_module.get_reminder(rid)
    assert r is not None
    assert r.id == rid
    assert r.text == "hi"


def test_init_db_has_template_id_column(main_module):
    # проверяем, что init_db не падает и колонка существует (миграция уже внутри)
    import sqlite3
    conn = sqlite3.connect(main_module.DB_PATH)
    c = conn.cursor()
    c.execute("PRAGMA table_info(reminders)")
    cols = [row[1] for row in c.fetchall()]
    conn.close()
    assert "template_id" in cols