import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


class DummyMessage:
    def __init__(self, text="source reminder"):
        self.chat = SimpleNamespace(id=456)
        self.text = text


class DummyQuery:
    def __init__(self, data):
        self.data = data
        self.message = DummyMessage()
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


class DummyContext:
    def __init__(self):
        self.bot = object()
        self.user_data = {}


def _reminder(rid=101, text="source reminder"):
    return SimpleNamespace(
        id=rid,
        chat_id=456,
        text=text,
        remind_at=datetime(2026, 6, 12, 10, 0, tzinfo=TZ),
        created_by=123,
        template_id=None,
    )


def test_done_clears_all_related_message_keyboards(main_module, monkeypatch):
    cleared = []
    acked = []

    async def fake_clear(bot, reminder_id):
        cleared.append((bot, reminder_id))

    monkeypatch.setattr(main_module, "get_reminder", lambda rid: _reminder(rid))
    monkeypatch.setattr(main_module, "mark_reminder_acked", lambda rid: acked.append(rid))
    monkeypatch.setattr(main_module, "clear_reminder_message_keyboards", fake_clear)

    query = DummyQuery("done:101")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(main_module.snooze_callback(update, context))

    assert acked == [101]
    assert cleared == [(context.bot, 101)]
    assert query.answers == [("Отмечено как завершенное", False)]
    assert query.edited_text == ["source reminder (завершено ✅)"]
    assert query.edited_reply_markup == [None]


def test_snooze_action_clears_all_related_message_keyboards(main_module, monkeypatch):
    cleared = []
    acked = []
    created = []

    async def fake_clear(bot, reminder_id):
        cleared.append((bot, reminder_id))

    monkeypatch.setattr(main_module, "datetime", SimpleNamespace(now=lambda tz=None: datetime(2026, 6, 12, 10, 0, tzinfo=TZ)))
    monkeypatch.setattr(main_module, "get_reminder", lambda rid: _reminder(rid))
    monkeypatch.setattr(main_module, "mark_reminder_acked", lambda rid: acked.append(rid))
    monkeypatch.setattr(main_module, "clear_reminder_message_keyboards", fake_clear)
    monkeypatch.setattr(
        main_module,
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

    query = DummyQuery("snooze:101:1h")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(main_module.snooze_callback(update, context))

    assert acked == [101]
    assert cleared == [(context.bot, 101)]
    assert created == [
        {
            "chat_id": 456,
            "text": "source reminder",
            "remind_at": datetime(2026, 6, 12, 11, 0, tzinfo=TZ),
            "created_by": 123,
            "template_id": None,
        }
    ]
    assert query.answers == [("Отложено до 12.06 11:00", False)]
    assert query.edited_text == ["source reminder\n\n(Отложено до 12.06 11:00)"]


def test_snooze_picktime_clears_all_related_message_keyboards(main_module, monkeypatch):
    cleared = []
    acked = []
    created = []

    async def fake_clear(bot, reminder_id):
        cleared.append((bot, reminder_id))

    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 10, 0, tzinfo=TZ))
    monkeypatch.setattr(main_module, "get_reminder", lambda rid: _reminder(rid))
    monkeypatch.setattr(main_module, "mark_reminder_acked", lambda rid: acked.append(rid))
    monkeypatch.setattr(main_module, "clear_reminder_message_keyboards", fake_clear)
    monkeypatch.setattr(
        main_module,
        "add_reminder",
        lambda chat_id, text, remind_at, created_by, template_id=None: created.append(remind_at) or 777,
    )

    query = DummyQuery("snooze_picktime:101:2026-06-12:11:30")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(main_module.snooze_callback(update, context))

    assert acked == [101]
    assert cleared == [(context.bot, 101)]
    assert created == [datetime(2026, 6, 12, 11, 30, tzinfo=TZ)]
    assert query.answers == [("Отложено до 12.06 11:30", False)]
    assert query.edited_text == ["source reminder\n\n(Отложено до 12.06 11:30)"]


def test_snooze_pickdate_does_not_clear_related_messages_yet(main_module, monkeypatch):
    cleared = []
    acked = []

    async def fake_clear(bot, reminder_id):
        cleared.append((bot, reminder_id))

    monkeypatch.setattr(main_module, "mark_reminder_acked", lambda rid: acked.append(rid))
    monkeypatch.setattr(main_module, "clear_reminder_message_keyboards", fake_clear)
    monkeypatch.setattr(main_module, "build_custom_time_keyboard", lambda rid, date_str: "time-kb")

    query = DummyQuery("snooze_pickdate:101:2026-06-12")
    update = DummyUpdate(query)
    context = DummyContext()

    asyncio.run(main_module.snooze_callback(update, context))

    assert acked == [101]
    assert cleared == []
    assert query.answers == [("Выбери время", False)]
    assert query.edited_reply_markup == ["time-kb"]
