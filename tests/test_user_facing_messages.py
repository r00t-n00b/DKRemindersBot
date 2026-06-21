import asyncio
from types import SimpleNamespace


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answers = []
        self.edited_text = None
        self.edited_text_kwargs = None
        self.edited_reply_markup = "not-called"

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edited_text = text
        self.edited_text_kwargs = kwargs

    async def edit_message_reply_markup(self, **kwargs):
        self.edited_reply_markup = kwargs.get("reply_markup")


def test_user_facing_message_constants_are_specific(main_module):
    m = main_module

    assert "Произошла ошибка" not in m.MSG_NOT_UNDERSTOOD_PLAIN_TEXT
    assert "напомни завтра в 18:00 поздравить Саню" in m.MSG_NOT_UNDERSTOOD_PLAIN_TEXT
    assert "/remind завтра 18:00 - поздравить Саню" in m.MSG_NOT_UNDERSTOOD_PLAIN_TEXT

    assert "/remind DD.MM HH:MM - текст" in m.MSG_REMIND_USAGE
    assert "/remind every Monday 10:00 - текст" in m.MSG_REMIND_USAGE
    assert "/remind\n- 28.11 12:00 - завтра футбол" in m.MSG_REMIND_USAGE

    assert m.MSG_INVALID_REMINDER_ID
    assert m.MSG_REMINDER_NOT_FOUND
    assert m.MSG_REMINDER_ALREADY_DELETED_TEXT
    assert m.MSG_DELETE_FAILED_TEXT


def test_created_delete_invalid_id_uses_central_messages(main_module):
    m = main_module

    query = FakeQuery("created_del:not-int")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})

    asyncio.run(m.created_delete_callback(update, context))

    assert query.answers == [(m.MSG_DELETE_FAILED_SHORT, {"show_alert": True})]
    assert query.edited_text == m.MSG_DELETE_FAILED_TEXT
    assert query.edited_text_kwargs == {"reply_markup": None}


def test_created_delete_missing_row_uses_central_messages(main_module, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "get_reminder_row", lambda rid: None)

    query = FakeQuery("created_del:123")
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})

    asyncio.run(m.created_delete_callback(update, context))

    assert query.answers == [(m.MSG_REMINDER_ALREADY_DELETED_ALERT, {"show_alert": True})]
    assert query.edited_text == m.MSG_REMINDER_ALREADY_DELETED_TEXT
    assert query.edited_text_kwargs == {"reply_markup": None}


def test_created_snooze_cancel_invalid_id_uses_central_message(main_module):
    m = main_module

    query = FakeQuery("created_snooze_cancel:not-int")
    update = SimpleNamespace(callback_query=query)

    asyncio.run(m.created_snooze_cancel_callback(update, SimpleNamespace()))

    assert query.answers == [(m.MSG_INVALID_REMINDER_ID, {"show_alert": True})]
    assert query.edited_reply_markup == "not-called"


def test_user_started_message_helper_mentions_start(main_module):
    msg = main_module.msg_user_has_not_started_bot("@someone")

    assert "@someone" in msg
    assert "Start" in msg
    assert "повтори команду" in msg


class FakeReplyMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakePrivateChat:
    PRIVATE = "private"

    def __init__(self, chat_id=12345):
        self.id = chat_id
        self.type = "private"


def test_group_username_error_message_is_not_misleading(main_module):
    msg = main_module.MSG_GROUP_USERNAME_PREFIX_FORBIDDEN

    assert "/remind 02.02 - test" in msg
    assert "Свободное «напомни ...» в группе не работает" in msg
    assert "напомни 2 февраля test" not in msg
    assert "/remind @someone 02.02 - test" in msg
    assert "/remind 02.02 - текст @someone" not in msg


def test_recurring_missing_dash_uses_human_message(main_module, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "Chat", FakePrivateChat)

    message = FakeReplyMessage("/remind every hour привет")
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=FakePrivateChat(12345),
        effective_user=SimpleNamespace(id=1000, username="tester", first_name="Tester"),
    )
    context = SimpleNamespace(args=["every", "hour", "привет"], user_data={})

    asyncio.run(m.remind_command(update, context))

    assert message.replies
    reply, kwargs = message.replies[0]
    assert reply == m.msg_recurring_missing_dash(is_private=True)
    assert "Не смог понять дату и текст" not in reply


class FakeGroupChatForRecurring:
    PRIVATE = "private"

    def __init__(self, chat_id=-100):
        self.id = chat_id
        self.type = "group"


class FakePrivateChatForRecurring:
    PRIVATE = "private"

    def __init__(self, chat_id=12345):
        self.id = chat_id
        self.type = "private"


class FakeReminderMessageForRecurring:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def test_group_username_error_does_not_suggest_plain_text_remind(main_module):
    msg = main_module.MSG_GROUP_USERNAME_PREFIX_FORBIDDEN

    assert "/remind 02.02 - test" in msg
    assert "Свободное «напомни ...» в группе не работает" in msg
    assert "напомни 2 февраля test" not in msg
    assert "/remind 02.02 - текст @someone" not in msg


def test_group_recurring_missing_dash_does_not_suggest_plain_text_remind(main_module):
    msg = main_module.msg_recurring_missing_dash(is_private=False)

    assert "/remind every hour - привет" in msg
    assert "Свободное «напомни ...» в группе не работает" in msg
    assert "напомни каждый час - привет" not in msg
    assert "/remind <alias> every hour - привет" in msg


def test_group_recurring_missing_dash_runtime_message_is_group_aware(main_module):
    m = main_module

    message = FakeReminderMessageForRecurring("/remind every hour привет")
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=FakeGroupChatForRecurring(-100),
        effective_user=SimpleNamespace(id=1000, username="tester", first_name="Tester"),
    )
    context = SimpleNamespace(args=["every", "hour", "привет"], user_data={})

    asyncio.run(m.remind_command(update, context))

    assert message.replies
    reply, _ = message.replies[0]
    assert reply == m.msg_recurring_missing_dash(is_private=False)
    assert "напомни каждый час - привет" not in reply


def test_recurring_parse_failed_runtime_message_is_informative(main_module):
    m = main_module

    message = FakeReminderMessageForRecurring("/remind every banana - привет")
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=FakePrivateChatForRecurring(12345),
        effective_user=SimpleNamespace(id=1000, username="tester", first_name="Tester"),
    )
    context = SimpleNamespace(args=["every", "banana", "-", "привет"], user_data={})

    asyncio.run(m.remind_command(update, context))

    assert message.replies
    reply, _ = message.replies[0]
    assert reply == m.msg_recurring_parse_failed(is_private=True)
    assert "Не смог понять повторяющийся формат" not in reply
    assert "/remind every hour - привет" in reply


def test_plain_text_not_understood_mentions_help(main_module):
    assert "Все варианты ремайндеров есть в /help." in main_module.MSG_NOT_UNDERSTOOD_PLAIN_TEXT


def test_recurring_messages_do_not_suggest_unsupported_every_hour(main_module):
    messages = [
        main_module.msg_recurring_missing_dash(is_private=True),
        main_module.msg_recurring_missing_dash(is_private=False),
        main_module.msg_recurring_parse_failed(is_private=True),
        main_module.msg_recurring_parse_failed(is_private=False),
    ]

    for msg in messages:
        assert "/remind every hour - привет" in msg
        assert "every 1 hour" not in msg


def test_user_has_not_started_message_has_no_artificial_newline(main_module):
    msg = main_module.msg_user_has_not_started_bot("@someone")

    assert "написать @someone в личку" in msg
    assert "написать \n" not in msg


def test_callback_error_messages_are_actionable(main_module):
    assert "/list" in main_module.MSG_UNEXPECTED_CALLBACK_ERROR
    assert "/list" in main_module.MSG_DELETE_SERIES_FAILED
    assert "/list" in main_module.MSG_UNDO_EXPIRED
    assert "/list" in main_module.MSG_UNDO_RESTORE_FAILED
    assert "/list" in main_module.MSG_USER_CONTEXT_MISSING
    assert "обычное личное напоминание" in main_module.MSG_EVENT_DATE_NOT_FOUND
    assert "выбери время заново" in main_module.MSG_UNKNOWN_TIME_OPTION.lower()


def test_plain_text_not_understood_mentions_help(main_module):
    assert "Все варианты ремайндеров есть в /help." in main_module.MSG_NOT_UNDERSTOOD_PLAIN_TEXT


def test_recurring_messages_do_not_suggest_unsupported_every_hour(main_module):
    messages = [
        main_module.msg_recurring_missing_dash(is_private=True),
        main_module.msg_recurring_missing_dash(is_private=False),
        main_module.msg_recurring_parse_failed(is_private=True),
        main_module.msg_recurring_parse_failed(is_private=False),
    ]

    for msg in messages:
        assert "/remind every hour - привет" in msg
        assert "every 1 hour" not in msg


def test_user_has_not_started_message_has_no_artificial_newline(main_module):
    msg = main_module.msg_user_has_not_started_bot("@someone")

    assert "написать @someone в личку" in msg
    assert "написать \n" not in msg


def test_callback_error_messages_are_actionable(main_module):
    assert "/list" in main_module.MSG_UNEXPECTED_CALLBACK_ERROR
    assert "/list" in main_module.MSG_DELETE_SERIES_FAILED
    assert "/list" in main_module.MSG_UNDO_EXPIRED
    assert "/list" in main_module.MSG_UNDO_RESTORE_FAILED
    assert "/list" in main_module.MSG_USER_CONTEXT_MISSING
    assert "обычное личное напоминание" in main_module.MSG_EVENT_DATE_NOT_FOUND
    assert "выбери время заново" in main_module.MSG_UNKNOWN_TIME_OPTION.lower()


def test_plain_text_not_understood_mentions_help(main_module):
    assert "Все варианты ремайндеров есть в /help." in main_module.MSG_NOT_UNDERSTOOD_PLAIN_TEXT


def test_recurring_messages_do_not_suggest_unsupported_every_hour(main_module):
    messages = [
        main_module.msg_recurring_missing_dash(is_private=True),
        main_module.msg_recurring_missing_dash(is_private=False),
        main_module.msg_recurring_parse_failed(is_private=True),
        main_module.msg_recurring_parse_failed(is_private=False),
    ]

    for msg in messages:
        assert "/remind every hour - привет" in msg
        assert "every 1 hour" not in msg


def test_user_has_not_started_message_has_no_artificial_newline(main_module):
    msg = main_module.msg_user_has_not_started_bot("@someone")

    assert "написать @someone в личку" in msg
    assert "написать \n" not in msg


def test_callback_error_messages_are_actionable(main_module):
    assert "/list" in main_module.MSG_UNEXPECTED_CALLBACK_ERROR
    assert "/list" in main_module.MSG_DELETE_SERIES_FAILED
    assert "/list" in main_module.MSG_UNDO_EXPIRED
    assert "/list" in main_module.MSG_UNDO_RESTORE_FAILED
    assert "/list" in main_module.MSG_USER_CONTEXT_MISSING
    assert "обычное личное напоминание" in main_module.MSG_EVENT_DATE_NOT_FOUND
    assert "выбери время заново" in main_module.MSG_UNKNOWN_TIME_OPTION.lower()


def test_recurring_messages_suggest_supported_every_hour(main_module):
    messages = [
        main_module.msg_recurring_missing_dash(is_private=True),
        main_module.msg_recurring_missing_dash(is_private=False),
        main_module.msg_recurring_parse_failed(is_private=True),
        main_module.msg_recurring_parse_failed(is_private=False),
    ]

    for msg in messages:
        assert "/remind every hour - привет" in msg
        assert "every 1 hour" not in msg
        assert "без числа сейчас не поддерживается" not in msg


def test_parse_recurring_supports_every_hour_without_explicit_number(main_module, fixed_now):
    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "every hour - привет",
        fixed_now,
    )

    assert text == "привет"
    assert pattern_type == "interval"
    assert payload == {"value": 1, "unit": "hours"}
    assert hour == 10
    assert minute == 0
    assert first_dt == fixed_now.replace(second=0, microsecond=0) + main_module.timedelta(hours=1)


def test_parse_recurring_supports_russian_every_hour_without_explicit_number(main_module, fixed_now):
    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "каждый час - привет",
        fixed_now,
    )

    assert text == "привет"
    assert pattern_type == "interval"
    assert payload == {"value": 1, "unit": "hours"}
    assert hour == 10
    assert minute == 0
    assert first_dt == fixed_now.replace(second=0, microsecond=0) + main_module.timedelta(hours=1)
