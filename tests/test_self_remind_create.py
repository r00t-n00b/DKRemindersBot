import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Europe/Madrid")

class MockButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class MockMarkup:
    def __init__(self, keyboard):
        self.keyboard = keyboard


class DummyQuery:
    def __init__(self, data: str, user_id: int, chat_title: str = "Тест"):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(
            chat=SimpleNamespace(title=chat_title),
        )
        self.answers = []
        self.edited_text = []
        self.edited_reply_markup = []

    async def answer(self, text=None, show_alert=False, **kwargs):
        self.answers.append((text, show_alert))

    async def edit_message_text(self, text, **kwargs):
        self.edited_text.append(text)

    async def edit_message_reply_markup(self, reply_markup=None):
        self.edited_reply_markup.append(reply_markup)


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


def test_self_remind_set_20m_creates_private_reminder(main_module, monkeypatch):
    m = main_module

    now = datetime(2026, 3, 1, 10, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "get_now", lambda: now)

    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555 if user_id == 42 else None)

    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="group reminder text",
            created_by=123,
            remind_at=now,
            template_id=None,
        ),
    )

    created = []

    def fake_add_reminder(*, chat_id, text, remind_at, created_by, template_id=None):
        created.append((chat_id, text, remind_at, created_by, template_id))
        return 777

    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    bot = FakeBot()

    async def fake_get_chat(chat_id):
        return SimpleNamespace(title="Тест-группа для бота")

    bot.get_chat = fake_get_chat
    query = DummyQuery(data="selfremind:set:123:20m", user_id=42, chat_title="Тест")
    upd = DummyUpdate(query)
    ctx = DummyContext(bot)

    asyncio.run(m.snooze_callback(upd, ctx))

    assert len(created) == 1

    chat_id, text, remind_at, created_by, template_id = created[0]

    assert chat_id == 555
    assert text == 'Из чата "Тест-группа для бота": group reminder text'
    assert remind_at == datetime(2026, 3, 1, 10, 20, tzinfo=TZ)
    assert created_by == 42
    assert template_id is None

    assert query.answers
    assert query.answers[-1][0] == "Личное напоминание создано"
    assert query.edited_text == ['Ок, напомню 01.03 10:20: Из чата "Тест-группа для бота": group reminder text']


def test_self_remind_set_tomorrow10_creates_private_reminder(main_module, monkeypatch):
    m = main_module

    now = datetime(2026, 3, 1, 10, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "get_now", lambda: now)

    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555 if user_id == 42 else None)

    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="group reminder text",
            created_by=123,
            remind_at=now,
            template_id=None,
        ),
    )

    created = []

    def fake_add_reminder(*, chat_id, text, remind_at, created_by, template_id=None):
        created.append((chat_id, text, remind_at, created_by, template_id))
        return 777

    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    bot = FakeBot()

    async def fake_get_chat(chat_id):
        return SimpleNamespace(title="Тест-группа для бота")

    bot.get_chat = fake_get_chat
    query = DummyQuery(data="selfremind:set:123:tomorrow11", user_id=42, chat_title="Тест")
    upd = DummyUpdate(query)
    ctx = DummyContext(bot)

    asyncio.run(m.snooze_callback(upd, ctx))

    assert len(created) == 1

    chat_id, text, remind_at, created_by, template_id = created[0]

    assert chat_id == 555
    assert text == 'Из чата "Тест-группа для бота": group reminder text'
    assert remind_at == datetime(2026, 3, 2, 10, 0, tzinfo=TZ)
    assert created_by == 42
    assert template_id is None

    assert query.answers
    assert query.answers[-1][0] == "Личное напоминание создано"
    assert query.edited_text == ['Ок, напомню 02.03 10:00: Из чата "Тест-группа для бота": group reminder text']

def test_self_remind_set_nextmon_creates_private_reminder(main_module, monkeypatch):
    m = main_module

    now = datetime(2026, 3, 1, 10, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "get_now", lambda: now)

    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555 if user_id == 42 else None)

    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="group reminder text",
            created_by=123,
            remind_at=now,
            template_id=None,
        ),
    )

    created = []

    def fake_add_reminder(*, chat_id, text, remind_at, created_by, template_id=None):
        created.append((chat_id, text, remind_at, created_by, template_id))
        return 777

    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    bot = FakeBot()

    async def fake_get_chat(chat_id):
        return SimpleNamespace(title="Тест-группа для бота")

    bot.get_chat = fake_get_chat
    query = DummyQuery(data="selfremind:set:123:nextmon", user_id=42, chat_title="Тест")
    upd = DummyUpdate(query)
    ctx = DummyContext(bot)

    asyncio.run(m.snooze_callback(upd, ctx))

    assert len(created) == 1

    chat_id, text, remind_at, created_by, template_id = created[0]

    assert chat_id == 555
    assert text == 'Из чата "Тест-группа для бота": group reminder text'
    assert remind_at == datetime(2026, 3, 2, 10, 0, tzinfo=TZ)
    assert created_by == 42
    assert template_id is None

    assert query.answers
    assert query.answers[-1][0] == "Личное напоминание создано"
    assert query.edited_text == ['Ок, напомню 02.03 10:00: Из чата "Тест-группа для бота": group reminder text']

def test_self_remind_picktime_creates_private_reminder_and_replaces_text(main_module, monkeypatch):
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
            remind_at=datetime(2026, 3, 1, 10, 0, tzinfo=TZ),
            template_id=None,
        ),
    )

    created = []

    def fake_add_reminder(*, chat_id, text, remind_at, created_by, template_id=None):
        created.append((chat_id, text, remind_at, created_by, template_id))
        return 777

    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    bot = FakeBot()

    async def fake_get_chat(chat_id):
        return SimpleNamespace(title="Тест-группа для бота")

    bot.get_chat = fake_get_chat
    monkeypatch.setattr(m, "get_now", lambda: datetime(2026, 3, 5, 17, 0, tzinfo=TZ))

    query = DummyQuery(data="selfremind:set:123:1h", user_id=42, chat_title="Тест")
    upd = DummyUpdate(query)
    ctx = DummyContext(bot)

    asyncio.run(m.snooze_callback(upd, ctx))

    assert len(created) == 1
    chat_id, text, remind_at, created_by, template_id = created[0]

    assert chat_id == 555
    assert text == 'Из чата "Тест-группа для бота": group reminder text'
    assert remind_at == datetime(2026, 3, 5, 18, 0, tzinfo=TZ)
    assert created_by == 42
    assert template_id is None

    assert query.answers
    assert query.answers[-1][0] == "Личное напоминание создано"
    assert query.edited_text == ['Ок, напомню 05.03 18:00: Из чата "Тест-группа для бота": group reminder text']

def test_self_remind_mode_event_with_parseable_event_shows_event_before_keyboard(main_module, monkeypatch):
    m = main_module

    event_at = datetime(2026, 3, 2, 18, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "get_now", lambda: datetime(2026, 3, 1, 10, 0, tzinfo=TZ))

    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555 if user_id == 42 else None)
    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="футбол завтра в 18:00",
            created_by=123,
            remind_at=datetime(2026, 3, 1, 10, 0, tzinfo=TZ),
            sent_at=datetime(2026, 3, 1, 10, 5, tzinfo=TZ),
            template_id=None,
        ),
    )
    monkeypatch.setattr(m, "extract_event_datetime_from_text", lambda text, base_now: event_at)
    event_keyboard_calls = []

    def fake_build_self_remind_event_before_keyboard(reminder_id):
        event_keyboard_calls.append(reminder_id)
        return ("EVENT_BEFORE", reminder_id)

    monkeypatch.setattr(
        m,
        "build_self_remind_event_before_keyboard",
        fake_build_self_remind_event_before_keyboard,
    )
    query = DummyQuery(data="selfremind:mode:123:event", user_id=42, chat_title="Тест")
    upd = DummyUpdate(query)
    ctx = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(upd, ctx))

    assert query.answers
    assert query.answers[-1] == ("Выбери время", False)
    assert query.edited_text
    assert "Я понял, что событие из напоминания состоится 02.03 18:00." in query.edited_text[-1]
    assert "За сколько до этого времени напомнить?" in query.edited_text[-1]
    assert event_keyboard_calls == [123]


def test_self_remind_mode_event_without_parseable_event_falls_back_to_regular_keyboard(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555 if user_id == 42 else None)
    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="просто текст без даты события",
            created_by=123,
            remind_at=datetime(2026, 3, 1, 10, 0, tzinfo=TZ),
            sent_at=datetime(2026, 3, 1, 10, 5, tzinfo=TZ),
            template_id=None,
        ),
    )
    monkeypatch.setattr(m, "extract_event_datetime_from_text", lambda text, base_now: None)
    choice_keyboard_calls = []

    def fake_build_self_remind_choice_keyboard(reminder_id):
        choice_keyboard_calls.append(reminder_id)
        return ("CHOICE", reminder_id)

    monkeypatch.setattr(
        m,
        "build_self_remind_choice_keyboard",
        fake_build_self_remind_choice_keyboard,
    )

    query = DummyQuery(data="selfremind:mode:123:event", user_id=42, chat_title="Тест")
    upd = DummyUpdate(query)
    ctx = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(upd, ctx))

    assert query.answers
    assert query.answers[-1] == ("Не смог понять дату события", False)
    assert choice_keyboard_calls == [123]


def test_self_remind_event_before_creates_private_reminder(main_module, monkeypatch):
    m = main_module

    event_at = datetime(2026, 3, 2, 18, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "get_now", lambda: datetime(2026, 3, 1, 10, 0, tzinfo=TZ))

    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555 if user_id == 42 else None)
    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="футбол завтра в 18:00",
            created_by=123,
            remind_at=datetime(2026, 3, 1, 10, 0, tzinfo=TZ),
            sent_at=datetime(2026, 3, 1, 10, 5, tzinfo=TZ),
            template_id=None,
        ),
    )
    monkeypatch.setattr(m, "extract_event_datetime_from_text", lambda text, base_now: event_at)
    monkeypatch.setattr(
        m,
        "normalize_relative_event_date_in_text",
        lambda text, event_at: "футбол 02.03 в 18:00",
    )

    created = []

    def fake_add_reminder(*, chat_id, text, remind_at, created_by, template_id=None):
        created.append((chat_id, text, remind_at, created_by, template_id))
        return 777

    monkeypatch.setattr(m, "add_reminder", fake_add_reminder)

    bot = FakeBot()

    async def fake_get_chat(chat_id):
        return SimpleNamespace(title="Тест-группа для бота")

    bot.get_chat = fake_get_chat

    query = DummyQuery(data="selfremind:event_before:123:1h", user_id=42, chat_title="Тест")
    upd = DummyUpdate(query)
    ctx = DummyContext(bot)

    asyncio.run(m.snooze_callback(upd, ctx))

    assert len(created) == 1

    chat_id, text, remind_at, created_by, template_id = created[0]

    assert chat_id == 555
    assert text == 'Из чата "Тест-группа для бота": футбол 02.03 в 18:00'
    assert remind_at == datetime(2026, 3, 2, 17, 0, tzinfo=TZ)
    assert created_by == 42
    assert template_id is None

    assert query.answers
    assert query.answers[-1][0] == "Личное напоминание создано"
    assert query.edited_text
    assert 'Ок, напомню 02.03 17:00: Из чата "Тест-группа для бота": футбол 02.03 в 18:00' in query.edited_text[-1]


def test_self_remind_back_returns_to_mode_keyboard(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="group reminder text",
            created_by=123,
            remind_at=datetime(2026, 3, 1, 10, 0, tzinfo=TZ),
            sent_at=datetime(2026, 3, 1, 10, 5, tzinfo=TZ),
            template_id=None,
        ),
    )
    mode_keyboard_calls = []

    def fake_build_self_remind_mode_keyboard(reminder_id):
        mode_keyboard_calls.append(reminder_id)
        return ("MODE", reminder_id)

    monkeypatch.setattr(
        m,
        "build_self_remind_mode_keyboard",
        fake_build_self_remind_mode_keyboard,
    )

    query = DummyQuery(data="selfremind:back:123", user_id=42, chat_title="Тест")
    upd = DummyUpdate(query)
    ctx = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(upd, ctx))

    assert query.answers
    assert query.answers[-1] == ("Вернул выбор", False)
    assert mode_keyboard_calls == [123]

def test_self_remind_cancel_personal_edits_message(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="group reminder text",
            created_by=123,
            remind_at=datetime(2026, 3, 1, 10, 0, tzinfo=TZ),
            sent_at=datetime(2026, 3, 1, 10, 5, tzinfo=TZ),
            template_id=None,
        ),
    )

    query = DummyQuery(data="selfremind:cancel_personal:123", user_id=42, chat_title="Тест")
    upd = DummyUpdate(query)
    ctx = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(upd, ctx))

    assert query.answers
    assert query.answers[-1] == ("Ок", False)
    assert query.edited_text
    assert query.edited_text[-1] == "Ок, личное напоминание не создаю."

def test_selfremind_caltoday_replaces_markup_with_today_calendar(main_module, monkeypatch):
    m = main_module
    fake_kb = object()
    calls = []

    monkeypatch.setattr(
        m,
        "build_custom_date_keyboard",
        lambda rid, year, month, callback_prefix: calls.append((rid, year, month, callback_prefix)) or fake_kb,
    )

    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "datetime", SimpleNamespace(now=lambda tz=None: now))

    query = DummyQuery("selfremind_caltoday:101", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert calls == [(101, 2026, 6, "selfremind")]
    assert query.edited_reply_markup == [fake_kb]
    assert query.answers == [(None, False)]


def test_selfremind_event_caltoday_uses_event_calendar_prefix(main_module, monkeypatch):
    m = main_module
    fake_kb = object()
    calls = []

    monkeypatch.setattr(
        m,
        "build_custom_date_keyboard",
        lambda rid, year, month, callback_prefix: calls.append((rid, year, month, callback_prefix)) or fake_kb,
    )

    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "datetime", SimpleNamespace(now=lambda tz=None: now))

    query = DummyQuery("selfremind_event_caltoday:101", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert calls == [(101, 2026, 6, "selfremind_event")]
    assert query.edited_reply_markup == [fake_kb]
    assert query.answers == [(None, False)]


def test_selfremind_pickdate_replaces_markup_with_time_keyboard(main_module, monkeypatch):
    m = main_module
    fake_kb = object()
    calls = []

    monkeypatch.setattr(
        m,
        "build_custom_time_keyboard",
        lambda rid, date_str, callback_prefix: calls.append((rid, date_str, callback_prefix)) or fake_kb,
    )

    query = DummyQuery("selfremind_pickdate:101:2026-06-12", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert calls == [(101, "2026-06-12", "selfremind")]
    assert query.edited_reply_markup == [fake_kb]
    assert query.answers == [("Выбери время", False)]


def test_selfremind_event_pickdate_uses_event_time_keyboard_prefix(main_module, monkeypatch):
    m = main_module
    fake_kb = object()
    calls = []

    monkeypatch.setattr(
        m,
        "build_custom_time_keyboard",
        lambda rid, date_str, callback_prefix: calls.append((rid, date_str, callback_prefix)) or fake_kb,
    )

    query = DummyQuery("selfremind_event_pickdate:101:2026-06-12", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert calls == [(101, "2026-06-12", "selfremind_event")]
    assert query.edited_reply_markup == [fake_kb]
    assert query.answers == [("Выбери время", False)]


def test_selfremind_picktime_creates_private_reminder(main_module, monkeypatch):
    m = main_module
    created = []

    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "get_now", lambda: now)
    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555 if user_id == 42 else None)
    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="source text",
            created_by=123,
            remind_at=now,
            template_id=None,
        ),
    )

    async def fake_title(context, src, query):
        return "Source Chat"

    monkeypatch.setattr(m, "get_source_chat_title_for_self_remind", fake_title)
    monkeypatch.setattr(m, "format_self_remind_text", lambda title, text: f"[{title}] {text}")
    monkeypatch.setattr(
        m,
        "add_reminder",
        lambda chat_id, text, remind_at, created_by, template_id=None: created.append(
            {
                "chat_id": chat_id,
                "text": text,
                "remind_at": remind_at,
                "created_by": created_by,
                "template_id": template_id,
            }
        ) or 777,
    )

    query = DummyQuery("selfremind_picktime:101:2026-06-12:11:30", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert created == [
        {
            "chat_id": 555,
            "text": "[Source Chat] source text",
            "remind_at": datetime(2026, 6, 12, 11, 30, tzinfo=TZ),
            "created_by": 42,
            "template_id": None,
        }
    ]
    assert query.edited_text == ["Ок, напомню 12.06 11:30: [Source Chat] source text"]
    assert query.answers == [("Личное напоминание создано", False)]


def test_selfremind_picktime_without_user_id_shows_alert(main_module):
    m = main_module

    query = DummyQuery("selfremind_picktime:101:2026-06-12:11:30", user_id=42)
    query.from_user = SimpleNamespace()
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [("Не удалось определить пользователя", True)]
    assert query.edited_text == []


def test_selfremind_picktime_without_private_chat_shows_start_alert(main_module, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: None)

    query = DummyQuery("selfremind_picktime:101:2026-06-12:11:30", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert len(query.answers) == 1
    assert query.answers[0][1] is True
    assert "Я еще с тобой не знаком" in query.answers[0][0]
    assert query.edited_text == []


def test_selfremind_picktime_missing_source_reminder_shows_alert(main_module, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555)
    monkeypatch.setattr(m, "get_reminder", lambda rid: None)

    query = DummyQuery("selfremind_picktime:101:2026-06-12:11:30", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [("Исходное напоминание не найдено", True)]
    assert query.edited_text == []


def test_selfremind_picktime_bad_datetime_shows_alert(main_module, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555)
    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="source text",
            created_by=123,
            remind_at=datetime(2026, 6, 12, 10, 0, tzinfo=TZ),
            template_id=None,
        ),
    )

    query = DummyQuery("selfremind_picktime:101:bad-date:bad-time", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [("Не смог понять дату/время", True)]
    assert query.edited_text == []


def test_selfremind_picktime_past_datetime_shows_alert(main_module, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "get_now", lambda: datetime(2026, 6, 12, 12, 0, tzinfo=TZ))
    monkeypatch.setattr(m, "get_user_chat_id_by_user_id", lambda user_id: 555)
    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="source text",
            created_by=123,
            remind_at=datetime(2026, 6, 12, 10, 0, tzinfo=TZ),
            template_id=None,
        ),
    )

    query = DummyQuery("selfremind_picktime:101:2026-06-12:11:30", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [("Это время уже прошло. Выбери другое время.", True)]
    assert query.edited_text == []


def test_selfremind_event_cancel_with_parseable_event_returns_event_before_options(main_module, monkeypatch):
    m = main_module
    fake_kb = object()
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)
    event_at = datetime(2026, 6, 13, 15, 30, tzinfo=TZ)

    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="event tomorrow at 15:30",
            created_by=123,
            remind_at=now,
            template_id=None,
        ),
    )
    monkeypatch.setattr(m, "get_self_remind_event_base", lambda src: now)
    monkeypatch.setattr(m, "extract_event_datetime_from_text", lambda text, base_now: event_at)
    monkeypatch.setattr(m, "build_self_remind_event_before_keyboard", lambda rid: fake_kb)

    query = DummyQuery("selfremind_event_cancel:101", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert len(query.edited_text) == 1
    assert "Я понял, что событие из напоминания состоится 13.06 15:30." in query.edited_text[0]
    assert "За сколько до этого времени напомнить?" in query.edited_text[0]
    assert query.answers == [("Вернул варианты до события", False)]


def test_selfremind_event_cancel_without_parseable_event_returns_regular_options(main_module, monkeypatch):
    m = main_module
    fake_kb = object()
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    monkeypatch.setattr(
        m,
        "get_reminder",
        lambda rid: SimpleNamespace(
            id=rid,
            chat_id=999,
            text="event without date",
            created_by=123,
            remind_at=now,
            template_id=None,
        ),
    )
    monkeypatch.setattr(m, "get_self_remind_event_base", lambda src: now)
    monkeypatch.setattr(m, "extract_event_datetime_from_text", lambda text, base_now: None)
    monkeypatch.setattr(m, "build_self_remind_choice_keyboard", lambda rid: fake_kb)

    query = DummyQuery("selfremind_event_cancel:101", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert len(query.edited_text) == 1
    assert "Я не смог понять дату события из текста." in query.edited_text[0]
    assert "Ты можешь поставить себе обычный ремайндер:" in query.edited_text[0]
    assert query.answers == [("Вернул варианты", False)]


def test_selfremind_event_cancel_bad_id_shows_alert(main_module):
    m = main_module

    query = DummyQuery("selfremind_event_cancel:not-int", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [("Некорректный reminder id", True)]
    assert query.edited_text == []


def test_selfremind_event_cancel_missing_source_shows_alert(main_module, monkeypatch):
    m = main_module
    monkeypatch.setattr(m, "get_reminder", lambda rid: None)

    query = DummyQuery("selfremind_event_cancel:101", user_id=42)
    update = DummyUpdate(query)
    context = DummyContext(FakeBot())

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [("Исходное напоминание не найдено", True)]
    assert query.edited_text == []
