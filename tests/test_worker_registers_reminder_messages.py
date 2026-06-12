import asyncio
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


class FakeBot:
    def __init__(self, message_id):
        self.message_id = message_id
        self.sent = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=self.message_id)


class FakeApp:
    def __init__(self, bot):
        self.bot = bot


async def _stop_after_first_sleep(*args, **kwargs):
    raise asyncio.CancelledError


async def _private_chat_type(*args, **kwargs):
    return "private"


async def _telegram_private_chat_type(main_module):
    return main_module.Chat.PRIVATE


def _mark_reminder_delivered_for_nudge(main_module, reminder_id, sent_at):
    conn = sqlite3.connect(main_module.DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        UPDATE reminders
        SET delivered = 1,
            sent_at = ?,
            acked = 0,
            nudge_count = 0
        WHERE id = ?
        """,
        (sent_at.isoformat(), reminder_id),
    )
    conn.commit()
    conn.close()


def test_reminders_worker_registers_delivery_message(main_module, monkeypatch):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)
    registered = []

    rid = main_module.add_reminder(
        chat_id=456,
        text="delivery tracking",
        remind_at=now - timedelta(seconds=1),
        created_by=123,
    )

    monkeypatch.setattr(main_module, "get_now", lambda: now)
    monkeypatch.setattr(main_module.asyncio, "sleep", _stop_after_first_sleep)
    monkeypatch.setattr(main_module, "_safe_get_chat_type", _private_chat_type)
    monkeypatch.setattr(main_module, "build_snooze_keyboard", lambda reminder_id: "snooze-kb")
    monkeypatch.setattr(
        main_module,
        "register_reminder_message",
        lambda reminder_id, chat_id, message_id, kind: registered.append(
            {
                "reminder_id": reminder_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "kind": kind,
            }
        ),
    )

    bot = FakeBot(message_id=9001)
    app = FakeApp(bot)

    try:
        asyncio.run(main_module.reminders_worker(app))
    except asyncio.CancelledError:
        pass

    assert bot.sent == [
        {
            "chat_id": 456,
            "text": "delivery tracking",
            "reply_markup": "snooze-kb",
        }
    ]
    assert registered == [
        {
            "reminder_id": rid,
            "chat_id": 456,
            "message_id": 9001,
            "kind": "delivery",
        }
    ]


def test_reminders_worker_skips_register_when_send_message_returns_no_message_id(main_module, monkeypatch):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)
    registered = []

    main_module.add_reminder(
        chat_id=456,
        text="delivery no message id",
        remind_at=now - timedelta(seconds=1),
        created_by=123,
    )

    class BotWithoutMessageId:
        async def send_message(self, **kwargs):
            return None

    monkeypatch.setattr(main_module, "get_now", lambda: now)
    monkeypatch.setattr(main_module.asyncio, "sleep", _stop_after_first_sleep)
    monkeypatch.setattr(main_module, "_safe_get_chat_type", _private_chat_type)
    monkeypatch.setattr(main_module, "build_snooze_keyboard", lambda reminder_id: "snooze-kb")
    monkeypatch.setattr(
        main_module,
        "register_reminder_message",
        lambda *args, **kwargs: registered.append((args, kwargs)),
    )

    app = FakeApp(BotWithoutMessageId())

    try:
        asyncio.run(main_module.reminders_worker(app))
    except asyncio.CancelledError:
        pass

    assert registered == []


def test_reminders_nudge_worker_registers_nudge_message(main_module, monkeypatch):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)
    registered = []

    rid = main_module.add_reminder(
        chat_id=456,
        text="nudge tracking",
        remind_at=now - timedelta(minutes=30),
        created_by=123,
    )
    _mark_reminder_delivered_for_nudge(
        main_module,
        rid,
        sent_at=now - timedelta(minutes=30),
    )

    monkeypatch.setattr(main_module, "get_now", lambda: now)
    monkeypatch.setattr(main_module.asyncio, "sleep", _stop_after_first_sleep)
    async def fake_safe_get_chat_type(app, chat_id):
        return main_module.Chat.PRIVATE

    monkeypatch.setattr(main_module, "_safe_get_chat_type", fake_safe_get_chat_type)
    monkeypatch.setattr(main_module, "build_snooze_keyboard", lambda reminder_id: "snooze-kb")
    monkeypatch.setattr(
        main_module,
        "register_reminder_message",
        lambda reminder_id, chat_id, message_id, kind: registered.append(
            {
                "reminder_id": reminder_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "kind": kind,
            }
        ),
    )

    bot = FakeBot(message_id=9002)
    app = FakeApp(bot)

    try:
        asyncio.run(main_module.reminders_nudge_worker(app))
    except asyncio.CancelledError:
        pass

    assert bot.sent == [
        {
            "chat_id": 456,
            "text": (
                "Ты никак не отреагировал на напоминание.\n"
                "Посмотри и нажми кнопку:\n\n"
                "nudge tracking"
            ),
            "reply_markup": "snooze-kb",
        }
    ]
    assert registered == [
        {
            "reminder_id": rid,
            "chat_id": 456,
            "message_id": 9002,
            "kind": "nudge",
        }
    ]
