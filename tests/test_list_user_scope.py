def test_list_user_scope_only_my_created(main_module, fixed_now):
    m = main_module

    owner_user_id = 2000
    owner_chat_id = 777000
    owner_username = "vasya"

    me_user_id = 1000

    m.upsert_user_chat(
        user_id=owner_user_id,
        chat_id=owner_chat_id,
        username=owner_username,
        first_name="Vasya",
        last_name=None,
    )

    dt1 = fixed_now.replace(day=29, hour=10, minute=0)
    dt2 = fixed_now.replace(day=29, hour=11, minute=0)

    id_my = m.add_reminder(
        chat_id=owner_chat_id,
        text="my reminder",
        remind_at=dt1,
        created_by=me_user_id,
    )
    m.add_reminder(
        chat_id=owner_chat_id,
        text="other reminder",
        remind_at=dt2,
        created_by=9999,
    )

    rows = m.get_active_reminders_created_by_for_chat(
        chat_id=owner_chat_id,
        created_by=me_user_id,
    )

    assert len(rows) == 1
    assert rows[0]["id"] == id_my
    assert rows[0]["text"] == "my reminder"


def test_get_private_chat_id_by_username(main_module):
    m = main_module

    m.upsert_user_chat(
        user_id=2000,
        chat_id=777000,
        username="vasya",
        first_name="Vasya",
        last_name=None,
    )

    assert m.get_private_chat_id_by_username("vasya") == 777000
    assert m.get_private_chat_id_by_username("@vasya") == 777000
    assert m.get_private_chat_id_by_username("nope") is None


# ===== НОВЫЕ ТЕСТЫ =====

def test_list_user_scope_shows_recurring_human(main_module, fixed_now):
    """
    Проверяем, что при /list @username
    recurring-напоминание имеет человекочитаемую регулярность.
    """
    m = main_module

    me_user_id = 1000
    owner_user_id = 2000
    owner_chat_id = 777000

    m.upsert_user_chat(
        user_id=owner_user_id,
        chat_id=owner_chat_id,
        username="vasya",
        first_name="Vasya",
        last_name=None,
    )

    tpl_id = m.create_recurring_template(
        chat_id=owner_chat_id,
        text="daily task",
        pattern_type="daily",
        payload={},
        time_hour=10,
        time_minute=0,
        created_by=me_user_id,
    )

    m.add_reminder(
        chat_id=owner_chat_id,
        text="daily task",
        remind_at=fixed_now.replace(day=29, hour=10, minute=0),
        created_by=me_user_id,
        template_id=tpl_id,
    )

    rows = m.get_active_reminders_created_by_for_chat(
        chat_id=owner_chat_id,
        created_by=me_user_id,
    )

    assert len(rows) == 1
    assert rows[0]["template_id"] == tpl_id

    tpl = m.get_recurring_template(tpl_id)
    human = m.format_recurring_human(tpl["pattern_type"], tpl["payload"])

    assert human is not None
    assert isinstance(human, str)
    assert human != ""


def test_delete_keeps_recurring_info(main_module, fixed_now):
    """
    Регрессия:
    после удаления одного ремайндера
    recurring-информация у оставшихся НЕ пропадает.
    """
    m = main_module

    chat_id = 12345
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

    r1 = m.add_reminder(
        chat_id=chat_id,
        text="weekly task",
        remind_at=fixed_now.replace(day=29, hour=10, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )
    r2 = m.add_reminder(
        chat_id=chat_id,
        text="one-off task",
        remind_at=fixed_now.replace(day=29, hour=12, minute=0),
        created_by=user_id,
    )

    # удаляем обычный
    deleted = m.delete_reminders([r2], chat_id)
    assert deleted == 1

    # получаем оставшиеся с join'ом
    conn = m.sqlite3.connect(m.DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        SELECT r.id, r.text, r.template_id, rt.pattern_type, rt.payload
        FROM reminders r
        LEFT JOIN recurring_templates rt ON rt.id = r.template_id
        WHERE r.chat_id = ? AND r.delivered = 0
        """,
        (chat_id,),
    )
    rows = c.fetchall()
    conn.close()

    assert len(rows) == 1
    rid, text, template_id, pattern_type, payload_json = rows[0]

    assert rid == r1
    assert template_id == tpl_id

    payload = {}
    if payload_json:
        payload = m.json.loads(payload_json)

    human = m.format_recurring_human(pattern_type, payload)
    assert human is not None
    assert human != ""