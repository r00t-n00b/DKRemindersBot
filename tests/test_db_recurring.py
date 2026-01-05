from datetime import timedelta


def test_recurring_template_create_get(main_module, fixed_now):
    tpl_id = main_module.create_recurring_template(
        chat_id=123,
        text="a",
        pattern_type="daily",
        payload={},
        time_hour=10,
        time_minute=0,
        created_by=1,
    )
    tpl = main_module.get_recurring_template(tpl_id)
    assert tpl is not None
    assert tpl["id"] == tpl_id
    assert tpl["active"] is True
    assert tpl["pattern_type"] == "daily"


def test_delete_reminders_deactivates_template(main_module, fixed_now):
    tpl_id = main_module.create_recurring_template(
        chat_id=123,
        text="a",
        pattern_type="daily",
        payload={},
        time_hour=10,
        time_minute=0,
        created_by=1,
    )
    rid = main_module.add_reminder(
        chat_id=123,
        text="a",
        remind_at=fixed_now + timedelta(minutes=1),
        created_by=1,
        template_id=tpl_id,
    )

    deleted = main_module.delete_reminders([rid], 123)
    assert deleted == 1

    tpl = main_module.get_recurring_template(tpl_id)
    assert tpl is not None
    assert tpl["active"] is False