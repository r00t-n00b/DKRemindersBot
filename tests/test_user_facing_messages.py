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
    assert "/remind завтра 18:00 - поздравить Саню" in m.MSG_NOT_UNDERSTOOD_PLAIN_TEXT
    assert "Подробнее: /help" in m.MSG_NOT_UNDERSTOOD_PLAIN_TEXT

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
