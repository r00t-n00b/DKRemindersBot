import asyncio
from types import SimpleNamespace


class FakeInlineKeyboardButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class FakeInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answers = []
        self.edited_text = None
        self.edited_text_kwargs = None
        self.edited_reply_markup = None

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edited_text = text
        self.edited_text_kwargs = kwargs

    async def edit_message_reply_markup(self, **kwargs):
        self.edited_reply_markup = kwargs.get("reply_markup")


def test_build_created_reminder_actions_keyboard(main_module, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "InlineKeyboardButton", FakeInlineKeyboardButton)
    monkeypatch.setattr(m, "InlineKeyboardMarkup", FakeInlineKeyboardMarkup)

    keyboard = m.build_created_reminder_actions_keyboard(123)

    assert keyboard.inline_keyboard[0][0].text == "Удалить"
    assert keyboard.inline_keyboard[0][0].callback_data == "created_del:123"
    assert keyboard.inline_keyboard[0][1].text == "Перенести"
    assert keyboard.inline_keyboard[0][1].callback_data == "created_resched:123"


def test_created_delete_callback_acks_reminder_and_edits_message(main_module, monkeypatch):
    m = main_module
    acked = []

    monkeypatch.setattr(m, "mark_reminder_acked", lambda rid: acked.append(rid))

    query = FakeQuery("created_del:456")
    update = SimpleNamespace(callback_query=query)

    asyncio.run(m.created_delete_callback(update, SimpleNamespace()))

    assert acked == [456]
    assert query.answers
    assert query.answers[0][0] == "Удалено"
    assert query.edited_text == "Удалил напоминание."
    assert query.edited_text_kwargs.get("reply_markup") is None


def test_created_reschedule_callback_replaces_keyboard_with_snooze_keyboard(main_module, monkeypatch):
    m = main_module
    snooze_keyboard = object()
    seen = []

    def fake_build_snooze_keyboard(rid):
        seen.append(rid)
        return snooze_keyboard

    monkeypatch.setattr(m, "build_snooze_keyboard", fake_build_snooze_keyboard)

    query = FakeQuery("created_resched:789")
    update = SimpleNamespace(callback_query=query)

    asyncio.run(m.created_reschedule_callback(update, SimpleNamespace()))

    assert seen == [789]
    assert query.answers
    assert query.edited_reply_markup is snooze_keyboard
