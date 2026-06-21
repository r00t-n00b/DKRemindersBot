import asyncio
from datetime import datetime, timedelta
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


class FixedDateTime(datetime):
    fixed_now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.fixed_now.replace(tzinfo=None)
        return cls.fixed_now.astimezone(tz)


class DummyMessage:
    def __init__(self, chat_id=456):
        self.chat = SimpleNamespace(id=chat_id)


class DummyQuery:
    def __init__(self, data, user_id=42, chat_id=456):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = DummyMessage(chat_id=chat_id)
        self.answers = []
        self.edited_text = []
        self.edited_reply_markup = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))

    async def edit_message_text(self, text, **kwargs):
        self.edited_text.append(text)

    async def edit_message_reply_markup(self, **kwargs):
        self.edited_reply_markup.append(kwargs.get("reply_markup"))


class DummyUpdate:
    def __init__(self, query):
        self.callback_query = query


class DummyBot:
    def __init__(self):
        self.edited_reply_markups = []

    async def edit_message_reply_markup(self, **kwargs):
        self.edited_reply_markups.append(kwargs)


class DummyContext:
    def __init__(self):
        self.user_data = {}
        self.bot = DummyBot()


def _reminder(rid=101, text="source reminder"):
    return SimpleNamespace(
        id=rid,
        chat_id=456,
        text=text,
        remind_at=datetime(2026, 6, 12, 9, 0, tzinfo=TZ),
        created_by=123,
        template_id=None,
    )


def test_snooze_20m_creates_new_reminder_acks_and_edits_message(main_module, monkeypatch):
    m = main_module
    created = []
    acked = []

    monkeypatch.setattr(m, "datetime", FixedDateTime)
    monkeypatch.setattr(m, "get_reminder", lambda rid: _reminder(rid))
    monkeypatch.setattr(m, "mark_reminder_acked", lambda rid: acked.append(rid))
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

    query = DummyQuery("snooze:101:20m")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert acked == [101]
    assert created == [
        {
            "chat_id": 456,
            "text": "source reminder",
            "remind_at": datetime(2026, 6, 12, 10, 20, tzinfo=TZ),
            "created_by": 123,
            "template_id": None,
        }
    ]
    assert query.edited_text == ["source reminder\n\n(Отложено до 12.06 10:20)"]
    assert query.answers == [("Отложено до 12.06 10:20", False)]


def test_snooze_tomorrow_sets_10_00(main_module, monkeypatch):
    m = main_module
    created = []

    monkeypatch.setattr(m, "datetime", FixedDateTime)
    monkeypatch.setattr(m, "get_reminder", lambda rid: _reminder(rid))
    monkeypatch.setattr(m, "mark_reminder_acked", lambda rid: None)
    monkeypatch.setattr(
        m,
        "add_reminder",
        lambda chat_id, text, remind_at, created_by, template_id=None: created.append(remind_at) or 777,
    )

    query = DummyQuery("snooze:101:tomorrow")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert created == [datetime(2026, 6, 13, 10, 0, tzinfo=TZ)]
    assert query.answers == [("Отложено до 13.06 10:00", False)]


def test_snooze_nextmon_sets_next_monday_10_00(main_module, monkeypatch):
    m = main_module
    created = []

    FixedDateTime.fixed_now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)  # Friday

    monkeypatch.setattr(m, "datetime", FixedDateTime)
    monkeypatch.setattr(m, "get_reminder", lambda rid: _reminder(rid))
    monkeypatch.setattr(m, "mark_reminder_acked", lambda rid: None)
    monkeypatch.setattr(
        m,
        "add_reminder",
        lambda chat_id, text, remind_at, created_by, template_id=None: created.append(remind_at) or 777,
    )

    query = DummyQuery("snooze:101:nextmon")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert created == [datetime(2026, 6, 15, 10, 0, tzinfo=TZ)]
    assert query.answers == [("Отложено до 15.06 10:00", False)]


def test_snooze_custom_replaces_markup_with_calendar_and_acks(main_module, monkeypatch):
    m = main_module
    fake_kb = object()
    acked = []

    monkeypatch.setattr(m, "get_reminder", lambda rid: _reminder(rid))
    monkeypatch.setattr(m, "mark_reminder_acked", lambda rid: acked.append(rid))
    monkeypatch.setattr(m, "build_custom_date_keyboard", lambda rid: fake_kb)

    query = DummyQuery("snooze:101:custom")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert acked == [101]
    assert query.edited_reply_markup == [fake_kb]
    assert query.answers == [("Выбери дату", False)]


def test_snooze_unknown_action_shows_alert(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(m, "get_reminder", lambda rid: _reminder(rid))

    query = DummyQuery("snooze:101:unknown")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [("Неизвестное действие", True)]
    assert query.edited_text == []
    assert query.edited_reply_markup == []


def test_snooze_missing_reminder_shows_alert(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(m, "get_reminder", lambda rid: None)

    query = DummyQuery("snooze:101:20m")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [("Напоминание не найдено", True)]
    assert query.edited_text == []


def test_snooze_cal_replaces_calendar_month(main_module, monkeypatch):
    m = main_module
    fake_kb = object()
    calls = []

    monkeypatch.setattr(
        m,
        "build_custom_date_keyboard",
        lambda rid, year, month: calls.append((rid, year, month)) or fake_kb,
    )

    query = DummyQuery("snooze_cal:101:2026-07")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert calls == [(101, 2026, 7)]
    assert query.edited_reply_markup == [fake_kb]
    assert query.answers == [(None, False)]


def test_snooze_caltoday_replaces_calendar_with_current_month(main_module, monkeypatch):
    m = main_module
    fake_kb = object()
    calls = []

    monkeypatch.setattr(m, "datetime", FixedDateTime)
    monkeypatch.setattr(
        m,
        "build_custom_date_keyboard",
        lambda rid, year, month: calls.append((rid, year, month)) or fake_kb,
    )

    query = DummyQuery("snooze_caltoday:101")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert calls == [(101, 2026, 6)]
    assert query.edited_reply_markup == [fake_kb]
    assert query.answers == [(None, False)]


def test_snooze_pickdate_acks_and_replaces_markup_with_time_keyboard(main_module, monkeypatch):
    m = main_module
    fake_kb = object()
    acked = []
    calls = []

    monkeypatch.setattr(m, "mark_reminder_acked", lambda rid: acked.append(rid))
    monkeypatch.setattr(
        m,
        "build_custom_time_keyboard",
        lambda rid, date_str: calls.append((rid, date_str)) or fake_kb,
    )

    query = DummyQuery("snooze_pickdate:101:2026-06-12")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert acked == [101]
    assert calls == [(101, "2026-06-12")]
    assert query.edited_reply_markup == [fake_kb]
    assert query.answers == [("Выбери время", False)]


def test_snooze_picktime_creates_new_reminder(main_module, monkeypatch):
    m = main_module
    created = []
    acked = []

    monkeypatch.setattr(m, "get_now", lambda: datetime(2026, 6, 12, 10, 0, tzinfo=TZ))
    monkeypatch.setattr(m, "get_reminder", lambda rid: _reminder(rid))
    monkeypatch.setattr(m, "mark_reminder_acked", lambda rid: acked.append(rid))
    monkeypatch.setattr(
        m,
        "add_reminder",
        lambda chat_id, text, remind_at, created_by, template_id=None: created.append(remind_at) or 777,
    )

    query = DummyQuery("snooze_picktime:101:2026-06-12:11:30")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert acked == [101]
    assert created == [datetime(2026, 6, 12, 11, 30, tzinfo=TZ)]
    assert query.edited_text == ["source reminder\n\n(Отложено до 12.06 11:30)"]
    assert query.answers == [("Отложено до 12.06 11:30", False)]


def test_snooze_picktime_missing_reminder_shows_alert(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(m, "get_reminder", lambda rid: None)

    query = DummyQuery("snooze_picktime:101:2026-06-12:11:30")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [("Напоминание не найдено", True)]


def test_snooze_picktime_bad_datetime_shows_alert(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(m, "get_reminder", lambda rid: _reminder(rid))

    query = DummyQuery("snooze_picktime:101:bad-date:bad-time")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [("Не смог понять дату/время", True)]


def test_snooze_picktime_past_datetime_shows_alert(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(m, "get_now", lambda: datetime(2026, 6, 12, 12, 0, tzinfo=TZ))
    monkeypatch.setattr(m, "get_reminder", lambda rid: _reminder(rid))

    query = DummyQuery("snooze_picktime:101:2026-06-12:11:30")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [("Это время уже прошло. Выбери другое время.", True)]


def test_snooze_cancel_valid_id_restores_snooze_keyboard_and_acks(main_module, monkeypatch):
    m = main_module
    fake_kb = object()
    acked = []

    monkeypatch.setattr(m, "mark_reminder_acked", lambda rid: acked.append(rid))
    monkeypatch.setattr(m, "build_snooze_keyboard", lambda rid: fake_kb)

    query = DummyQuery("snooze_cancel:101")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert acked == [101]
    assert query.edited_reply_markup == [fake_kb]
    assert query.answers == [("Вернул варианты", False)]


def test_snooze_cancel_bad_id_shows_alert(main_module):
    m = main_module

    query = DummyQuery("snooze_cancel:not-int")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [("Некорректный reminder id", True)]


def test_snooze_noop_only_answers(main_module):
    m = main_module

    query = DummyQuery("noop")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert query.answers == [(None, False)]
    assert query.edited_text == []
    assert query.edited_reply_markup == []


def test_snooze_edit_text_failure_falls_back_to_remove_markup(main_module, monkeypatch):
    m = main_module
    removed_markups = []

    class FailingEditQuery(DummyQuery):
        async def edit_message_text(self, text, **kwargs):
            raise RuntimeError("telegram edit failed")

        async def edit_message_reply_markup(self, **kwargs):
            removed_markups.append(kwargs.get("reply_markup"))

    monkeypatch.setattr(m, "datetime", FixedDateTime)
    monkeypatch.setattr(m, "get_reminder", lambda rid: _reminder(rid))
    monkeypatch.setattr(m, "mark_reminder_acked", lambda rid: None)
    monkeypatch.setattr(m, "add_reminder", lambda **kwargs: 777)

    query = FailingEditQuery("snooze:101:1h")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(m.snooze_callback(update, context))

    assert removed_markups == [None]
    assert query.answers == [("Отложено до 12.06 11:00", False)]
