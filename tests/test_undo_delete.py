def test_delete_snapshot_and_restore_oneoff(main_module, fixed_now):
    m = main_module

    chat_id = 111
    user_id = 1000

    rid = m.add_reminder(
        chat_id=chat_id,
        text="oneoff",
        remind_at=fixed_now.replace(day=29, hour=12, minute=0),
        created_by=user_id,
    )

    snap = m.delete_reminder_with_snapshot(rid, chat_id)
    assert snap is not None

    # удалено
    assert m.get_reminder_row(rid) is None

    new_id = m.restore_deleted_snapshot(snap)
    assert new_id is not None

    r2 = m.get_reminder_row(int(new_id))
    assert r2 is not None
    assert r2["chat_id"] == chat_id
    assert r2["text"] == "oneoff"
    assert r2["delivered"] == 0


def test_delete_snapshot_and_restore_recurring(main_module, fixed_now):
    m = main_module

    chat_id = 222
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="weekly task",
        pattern_type="weekly",
        payload={"weekday": 0},
        time_hour=10,
        time_minute=0,
        created_by=user_id,
    )

    rid = m.add_reminder(
        chat_id=chat_id,
        text="weekly task",
        remind_at=fixed_now.replace(day=29, hour=10, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )

    snap = m.delete_reminder_with_snapshot(rid, chat_id)
    assert snap is not None
    assert m.get_reminder_row(rid) is None

    new_id = m.restore_deleted_snapshot(snap)
    assert new_id is not None

    r2 = m.get_reminder_row(int(new_id))
    assert r2 is not None
    assert r2["chat_id"] == chat_id
    assert r2["text"] == "weekly task"
    assert r2["template_id"] is not None

    # human форматтер не обязателен, но можно чекнуть что не падает
    tpl = m.get_recurring_template(int(r2["template_id"]))
    assert tpl is not None