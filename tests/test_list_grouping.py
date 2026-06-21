import asyncio
from datetime import timedelta
from types import SimpleNamespace


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeUpdate:
    def __init__(self, chat_id=12345, user_id=1000):
        self.effective_chat = SimpleNamespace(id=chat_id, type="private")
        self.effective_user = SimpleNamespace(id=user_id, username="tester", first_name="Tester")
        self.effective_message = FakeMessage()


class FakeContext:
    def __init__(self):
        self.args = []
        self.user_data = {}


class FakeInlineKeyboardButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class FakeInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def test_list_groups_reminders_by_today_tomorrow_later(main_module, fixed_now, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "InlineKeyboardButton", FakeInlineKeyboardButton)
    monkeypatch.setattr(m, "InlineKeyboardMarkup", FakeInlineKeyboardMarkup)
    monkeypatch.setattr(m, "get_now", lambda: fixed_now)
    monkeypatch.setattr(m, "get_now", lambda: fixed_now)

    chat_id = 12345
    user_id = 1000

    today_id = m.add_reminder(
        chat_id=chat_id,
        text="today task",
        remind_at=fixed_now.replace(hour=18, minute=0),
        created_by=user_id,
    )
    tomorrow_id = m.add_reminder(
        chat_id=chat_id,
        text="tomorrow task",
        remind_at=(fixed_now + timedelta(days=1)).replace(hour=10, minute=30),
        created_by=user_id,
    )
    later_id = m.add_reminder(
        chat_id=chat_id,
        text="later task",
        remind_at=(fixed_now + timedelta(days=10)).replace(hour=11, minute=0),
        created_by=user_id,
    )

    update = FakeUpdate(chat_id=chat_id, user_id=user_id)
    context = FakeContext()

    asyncio.run(m.list_command(update, context))

    assert update.effective_message.replies
    reply, kwargs = update.effective_message.replies[0]

    assert reply.startswith("Активные напоминания:\n\n")

    assert "Сегодня\n1. 18:00 - today task" in reply
    assert "Завтра\n2. 10:30 - tomorrow task" in reply
    assert "Позже\n3. " in reply
    assert " - later task" in reply

    assert context.user_data["list_ids"] == [today_id, tomorrow_id, later_id]
    assert context.user_data["list_chat_id"] == chat_id

    keyboard = kwargs.get("reply_markup")
    assert keyboard is not None
    assert keyboard.inline_keyboard[0][0].text == "❌1"
    assert keyboard.inline_keyboard[0][0].callback_data == "del:1"


def test_list_preserves_recurring_suffix_inside_group(main_module, fixed_now, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "InlineKeyboardButton", FakeInlineKeyboardButton)
    monkeypatch.setattr(m, "InlineKeyboardMarkup", FakeInlineKeyboardMarkup)
    monkeypatch.setattr(m, "get_now", lambda: fixed_now)

    chat_id = 12345
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
    reminder_id = m.add_reminder(
        chat_id=chat_id,
        text="daily task",
        remind_at=fixed_now.replace(hour=10, minute=0),
        created_by=user_id,
        template_id=tpl_id,
    )

    update = FakeUpdate(chat_id=chat_id, user_id=user_id)
    context = FakeContext()

    asyncio.run(m.list_command(update, context))

    reply, _ = update.effective_message.replies[0]

    assert "Сегодня\n1. 10:00 - daily task  🔁" in reply
    assert context.user_data["list_ids"] == [reminder_id]


class FakeCallbackMessage:
    def __init__(self, chat_id=12345):
        self.chat = SimpleNamespace(id=chat_id, type="private")
        self.edits = []
        self.replies = []

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeCallbackQuery:
    def __init__(self, data, message):
        self.data = data
        self.message = message
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        await self.message.edit_message_text(text, **kwargs)


def test_delete_from_list_preserves_today_tomorrow_later_grouping(main_module, fixed_now, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "InlineKeyboardButton", FakeInlineKeyboardButton)
    monkeypatch.setattr(m, "InlineKeyboardMarkup", FakeInlineKeyboardMarkup)
    monkeypatch.setattr(m, "get_now", lambda: fixed_now)

    chat_id = 12345
    user_id = 1000

    today_id = m.add_reminder(
        chat_id=chat_id,
        text="today task",
        remind_at=fixed_now.replace(hour=18, minute=0),
        created_by=user_id,
    )
    tomorrow_id = m.add_reminder(
        chat_id=chat_id,
        text="tomorrow task",
        remind_at=(fixed_now + timedelta(days=1)).replace(hour=10, minute=30),
        created_by=user_id,
    )
    later_id = m.add_reminder(
        chat_id=chat_id,
        text="later task",
        remind_at=(fixed_now + timedelta(days=10)).replace(hour=11, minute=0),
        created_by=user_id,
    )

    context = FakeContext()
    update = FakeUpdate(chat_id=chat_id, user_id=user_id)
    asyncio.run(m.list_command(update, context))

    assert context.user_data["list_ids"] == [today_id, tomorrow_id, later_id]

    callback_message = FakeCallbackMessage(chat_id=chat_id)
    query = FakeCallbackQuery("del:1", callback_message)
    callback_update = SimpleNamespace(callback_query=query)

    asyncio.run(m.delete_callback(callback_update, context))

    assert query.answers
    assert callback_message.edits

    edited_text, kwargs = callback_message.edits[0]

    assert "Сегодня\n" not in edited_text
    assert "Завтра\n1. 10:30 - tomorrow task" in edited_text
    assert "Позже\n2. " in edited_text
    assert " - later task" in edited_text
    assert context.user_data["list_ids"] == [tomorrow_id, later_id]

    keyboard = kwargs.get("reply_markup")
    assert keyboard is not None
    assert keyboard.inline_keyboard[0][0].text == "❌1"
    assert keyboard.inline_keyboard[0][0].callback_data == "del:1"
