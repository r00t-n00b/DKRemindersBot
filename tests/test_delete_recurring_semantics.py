from datetime import datetime


def test_delete_single_recurring_does_not_deactivate_template(main_module, fixed_now):
    m = main_module
    chat_id = 123
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="weekly task",
        pattern_type="weekly",
        payload={"weekday": 3},
        time_hour=20,
        time_minute=30,
        created_by=user_id,
    )

    r1 = m.add_reminder(
        chat_id=chat_id,
        text="weekly task",
        remind_at=fixed_now.replace(day=29, hour=20, minute=30),
        created_by=user_id,
        template_id=tpl_id,
    )
    r2 = m.add_reminder(
        chat_id=chat_id,
        text="weekly task",
        remind_at=fixed_now.replace(day=30, hour=20, minute=30),
        created_by=user_id,
        template_id=tpl_id,
    )

    snap = m.delete_single_reminder_with_snapshot(r1, chat_id)
    assert snap is not None
    assert snap["kind"] == "single"

    # template должен остаться active
    tpl = m.get_recurring_template(int(tpl_id))
    assert tpl is not None
    assert tpl["active"] is True

    # второй инстанс должен остаться
    row2 = m.get_reminder_row(r2)
    assert row2 is not None
    assert int(row2["template_id"]) == int(tpl_id)


def test_delete_series_deactivates_template_and_deletes_all(main_module, fixed_now):
    m = main_module
    chat_id = 124
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="daily task",
        pattern_type="daily",
        payload={},
        time_hour=10,
        time_minute=0,
        created_by=user_id,
    )

    r1 = m.add_reminder(
        chat_id=chat_id,
        text="daily task",
        remind_at=fixed_now.replace(day=29, hour=10, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )
    r2 = m.add_reminder(
        chat_id=chat_id,
        text="daily task",
        remind_at=fixed_now.replace(day=30, hour=10, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )

    snap = m.delete_recurring_series_with_snapshot(tpl_id, chat_id)
    assert snap is not None
    assert snap["kind"] == "series"
    assert snap["template"]["id"] == tpl_id
    assert len(snap["reminders"]) == 2

    # reminders удалены
    assert m.get_reminder_row(r1) is None
    assert m.get_reminder_row(r2) is None

    # template должен стать inactive
    tpl = m.get_recurring_template(int(tpl_id))
    assert tpl is not None
    assert tpl["active"] is False


def test_undo_single_restores_reminder_and_keeps_template(main_module, fixed_now):
    m = main_module
    chat_id = 125
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="weekly task",
        pattern_type="weekly",
        payload={"weekday": 0},
        time_hour=9,
        time_minute=0,
        created_by=user_id,
    )

    r1 = m.add_reminder(
        chat_id=chat_id,
        text="weekly task",
        remind_at=fixed_now.replace(day=29, hour=9, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )

    snap = m.delete_single_reminder_with_snapshot(r1, chat_id)
    assert snap is not None
    assert m.get_reminder_row(r1) is None

    restored = m.restore_deleted_snapshot(snap)
    assert isinstance(restored, int)

    restored_row = m.get_reminder_row(int(restored))
    assert restored_row is not None
    assert restored_row["text"] == "weekly task"
    assert int(restored_row["template_id"]) == int(tpl_id)

    tpl = m.get_recurring_template(int(tpl_id))
    assert tpl is not None
    assert tpl["active"] is True


def test_undo_series_restores_template_and_all_reminders(main_module, fixed_now):
    m = main_module
    chat_id = 126
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="monthly task",
        pattern_type="monthly",
        payload={"day": 15},
        time_hour=12,
        time_minute=0,
        created_by=user_id,
    )

    r1_dt = fixed_now.replace(day=29, hour=12, minute=0)
    r2_dt = fixed_now.replace(day=30, hour=12, minute=0)

    r1 = m.add_reminder(
        chat_id=chat_id,
        text="monthly task",
        remind_at=r1_dt,
        created_by=user_id,
        template_id=tpl_id,
    )
    r2 = m.add_reminder(
        chat_id=chat_id,
        text="monthly task",
        remind_at=r2_dt,
        created_by=user_id,
        template_id=tpl_id,
    )

    snap = m.delete_recurring_series_with_snapshot(tpl_id, chat_id)
    assert snap is not None
    assert m.get_reminder_row(r1) is None
    assert m.get_reminder_row(r2) is None

    tpl = m.get_recurring_template(int(tpl_id))
    assert tpl is not None
    assert tpl["active"] is False

    restored = m.restore_deleted_snapshot(snap)
    assert isinstance(restored, list)
    assert len(restored) == 2

    tpl2 = m.get_recurring_template(int(tpl_id))
    assert tpl2 is not None
    assert tpl2["active"] is True

    # проверим, что инстансы восстановились и привязаны к тому же template_id
    for new_id in restored:
        rr = m.get_reminder_row(int(new_id))
        assert rr is not None
        assert int(rr["template_id"]) == int(tpl_id)
        assert rr["text"] == "monthly task"