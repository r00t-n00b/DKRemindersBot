import asyncio
from types import SimpleNamespace


class DummyQuery:
    def __init__(self, data: str, user_id: int, text: str = "group reminder text", chat_title: str = "Тест"):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(
            text=text,
            chat=SimpleNamespace(title=chat_title),
        )
        self.answers = []
        self.edited_reply_markup = []
        self.edited_text = []

    async def answer(self, text=None, show_alert=False, **kwargs):
        self.answers.append((text, show_alert))

    async def edit_message_reply_markup(self, reply_markup=None):
        self.edited_reply_markup.append(reply_markup)

    async def edit_message_text(self, text, **kwargs):
        self.edited_text.append(text)


class DummyUpdate:
    def __init__(self, query):
        self.callback_query = query


class DummyContext:
    def __init__(self, bot):
        self.bot = bot


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))


def test_self_remind_ask_sends_options_to_private_chat(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555 if user_id == 42 else None)
    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="group reminder text",
            created_by=123,
            template_id=None,
        ),
    )
    monkeypatch.setattr(m, "InlineKeyboardButton", lambda text, callback_data=None: SimpleNamespace(text=text, callback_data=callback_data))
    monkeypatch.setattr(m, "InlineKeyboardMarkup", lambda inline_keyboard: SimpleNamespace(inline_keyboard=inline_keyboard))

    bot = FakeBot()

    async def fake_get_chat(chat_id):
        return SimpleNamespace(title="Тест-группа для бота")

    bot.get_chat = fake_get_chat

    query = DummyQuery(data="selfremind:ask:123", user_id=42, text="group reminder text", chat_title="Личка")
    upd = DummyUpdate(query)
    ctx = DummyContext(bot)

    asyncio.run(m.snooze_callback(upd, ctx))

    assert query.answers
    assert query.answers[-1][0] == "Отправил варианты в личку"

    assert len(bot.sent) == 1
    chat_id, text, markup = bot.sent[0]

    assert chat_id == 555
    assert text == 'Как тебе напомнить о "group reminder text" из чата "Тест-группа для бота"?'

    buttons = [
        btn.text
        for row in markup.inline_keyboard
        for btn in row
    ]
    callback_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
    ]

    assert buttons == [
        "📅 Обычное напоминание",
        '⏰ Напоминание "до события"',
        "✅ Я передумал, напоминание не нужно",
    ]
    assert callback_data == [
        "selfremind:mode:123:regular",
        "selfremind:mode:123:event",
        "selfremind:cancel_personal:123",
    ]


def test_self_remind_ask_without_private_chat_shows_popup(main_module):
    m = main_module

    bot = FakeBot()
    query = DummyQuery(data="selfremind:ask:123", user_id=42)
    upd = DummyUpdate(query)
    ctx = DummyContext(bot)

    asyncio.run(m.snooze_callback(upd, ctx))

    assert bot.sent == []
    assert query.answers
    assert query.answers[-1] == ("Я еще с тобой не знаком. Открой бота в личке, отправь ему /start, а потом снова нажми кнопку в этом чате", True)


def test_self_remind_custom_opens_calendar(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555 if user_id == 42 else None)
    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="group reminder text",
            created_by=123,
            template_id=None,
        ),
    )
    monkeypatch.setattr(
        m,
        "build_custom_date_keyboard",
        lambda reminder_id, year=None, month=None, callback_prefix="snooze": ("CAL", reminder_id, callback_prefix),
    )

    query = DummyQuery(data="selfremind:set:123:custom", user_id=42)
    upd = DummyUpdate(query)
    ctx = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(upd, ctx))

    assert query.answers
    assert query.answers[-1] == ("Выбери дату", False)
    assert query.edited_reply_markup == [("CAL", 123, "selfremind")]


def test_self_remind_cancel_returns_to_default_choice_keyboard(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="group reminder text",
            created_by=123,
            template_id=None,
        ),
    )
    monkeypatch.setattr(
        m,
        "build_self_remind_choice_keyboard",
        lambda reminder_id: ("CHOICE", reminder_id),
    )

    query = DummyQuery(data="selfremind_cancel:123", user_id=42, text="old text", chat_title="Тест")
    upd = DummyUpdate(query)
    ctx = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(upd, ctx))

    assert query.answers
    assert query.answers[-1] == ("Вернул варианты", False)
    assert query.edited_text == ['Когда напомнить тебе о "group reminder text" из чата "Тест"?']
    assert query.edited_reply_markup == [("CHOICE", 123)]