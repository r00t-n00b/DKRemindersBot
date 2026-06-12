def test_delete_recurring_one_reschedules_next(main_module, fixed_now):
    m = main_module
    chat_id = 111
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="series",
        pattern_type="daily",
        payload={},
        time_hour=23,
        time_minute=0,
        created_by=user_id,
    )

    r1 = m.add_reminder(
        chat_id=chat_id,
        text="series",
        remind_at=fixed_now.replace(day=29, hour=23, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )

    snap = m.delete_recurring_one_instance_and_reschedule(r1, chat_id)
    assert snap is not None
    assert snap["mode"] == "one"
    assert snap["next_created_id"] is not None

    # template должен остаться активным
    tpl = m.get_recurring_template(tpl_id)
    assert tpl is not None
    assert tpl["active"] is True

    # должен существовать новый инстанс
    rows = m.get_active_reminders_for_chat(chat_id)
    assert len(rows) == 1
    assert rows[0]["template_id"] == tpl_id


def test_delete_recurring_series_deactivates_template(main_module, fixed_now):
    m = main_module
    chat_id = 222
    user_id = 1000

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="series",
        pattern_type="daily",
        payload={},
        time_hour=23,
        time_minute=0,
        created_by=user_id,
    )

    m.add_reminder(
        chat_id=chat_id,
        text="series",
        remind_at=fixed_now.replace(day=29, hour=23, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )

    deleted = m.delete_recurring_series(tpl_id, chat_id)
    assert deleted >= 1

    tpl = m.get_recurring_template(tpl_id)
    assert tpl is not None
    assert tpl["active"] is False

def test_list_shows_next_after_delete_one_recurring(main_module, fixed_now):
    m = main_module
    chat_id = 1
    user_id = 100

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="series",
        pattern_type="daily",
        payload={},
        time_hour=23,
        time_minute=0,
        created_by=user_id,
    )

    r1 = m.add_reminder(
        chat_id=chat_id,
        text="series",
        remind_at=fixed_now.replace(day=29, hour=23),
        created_by=user_id,
        template_id=tpl_id,
    )

    m.delete_recurring_one_instance_and_reschedule(r1, chat_id)

    rows = m.get_active_reminders_for_chat(chat_id)
    assert len(rows) == 1
    assert rows[0]["template_id"] == tpl_id

def test_delete_one_does_not_deactivate_template(main_module, fixed_now):
    m = main_module
    chat_id = 1
    user_id = 100

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="series",
        pattern_type="daily",
        payload={},
        time_hour=10,
        time_minute=0,
        created_by=user_id,
    )

    r = m.add_reminder(
        chat_id=chat_id,
        text="series",
        remind_at=fixed_now.replace(hour=10),
        created_by=user_id,
        template_id=tpl_id,
    )

    m.delete_recurring_one_instance_and_reschedule(r, chat_id)

    tpl = m.get_recurring_template(tpl_id)
    assert tpl["active"] is True

def test_delete_series_removes_all_instances(main_module, fixed_now):
    m = main_module
    chat_id = 1
    user_id = 100

    tpl_id = m.create_recurring_template(
        chat_id=chat_id,
        text="series",
        pattern_type="daily",
        payload={},
        time_hour=10,
        time_minute=0,
        created_by=user_id,
    )

    m.add_reminder(
        chat_id=chat_id,
        text="series",
        remind_at=fixed_now.replace(hour=10),
        created_by=user_id,
        template_id=tpl_id,
    )

    snap = m.delete_recurring_series_with_snapshot(tpl_id, chat_id)
    assert snap is not None

    rows = m.get_active_reminders_for_chat(chat_id)
    assert rows == []