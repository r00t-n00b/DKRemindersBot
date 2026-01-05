def test_list_user_scope_only_my_created(main_module, fixed_now):
    m = main_module

    # Допустим, "пользователь", которому ставим, уже писал боту
    # Мы руками положим запись в user_chats через функцию (если она есть)
    # Если нет функции, вставим прямо SQL (см. ниже).
    owner_user_id = 2000
    owner_chat_id = 777000
    owner_username = "vasya"

    # "я", кто ставит напоминания
    me_user_id = 1000

    # 1) Регистрируем связь username -> chat_id
    # Если у тебя есть функция upsert_user_chat - используем ее
    m.upsert_user_chat(
        user_id=owner_user_id,
        chat_id=owner_chat_id,
        username=owner_username,
        first_name="Vasya",
        last_name=None,
    )

    # 2) Создаем 2 напоминания в private chat Васи:
    # одно создано мной, другое создано кем-то еще
    dt1 = fixed_now.replace(day=29, hour=10, minute=0)
    dt2 = fixed_now.replace(day=29, hour=11, minute=0)

    id_my = m.add_reminder(
        chat_id=owner_chat_id,
        text="my reminder",
        remind_at=dt1,
        created_by=me_user_id,
    )
    id_other = m.add_reminder(
        chat_id=owner_chat_id,
        text="other reminder",
        remind_at=dt2,
        created_by=9999,
    )

    rows = m.get_active_reminders_created_by_for_chat(
        chat_id=owner_chat_id,
        created_by=me_user_id,
    )

    # Должно вернуть только мое
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