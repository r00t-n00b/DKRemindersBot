import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


class DummyMessage:
    def __init__(self, text):
        self.text = text
        self.voice = None
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def _mk_private(text, user_id=123, chat_id=456):
    message = DummyMessage(text)
    chat = SimpleNamespace(id=chat_id, type="private")
    user = SimpleNamespace(id=user_id, username="u", first_name="U", last_name="L")
    update = SimpleNamespace(
        effective_chat=chat,
        effective_message=message,
        effective_user=user,
        message=message,
    )
    context = SimpleNamespace(args=[], user_data={})
    return update, context, message


def _capture_add_reminder(main_module, monkeypatch):
    created = []

    def fake_add_reminder(chat_id, text, remind_at, created_by=None, template_id=None):
        created.append(
            {
                "chat_id": chat_id,
                "text": text,
                "remind_at": remind_at,
                "created_by": created_by,
                "template_id": template_id,
            }
        )
        return 777 + len(created)

    monkeypatch.setattr(main_module, "add_reminder", fake_add_reminder)
    return created


def test_remind_nested_ru_remind_evening_realistic_path(main_module, monkeypatch):
    created = _capture_add_reminder(main_module, monkeypatch)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 17, 30, tzinfo=TZ))

    update, context, message = _mk_private("/remind напомни завтра вечером купить молоко")

    asyncio.run(main_module.remind_command(update, context))

    assert created == [
        {
            "chat_id": 456,
            "text": "купить молоко",
            "remind_at": datetime(2026, 6, 13, 18, 0, tzinfo=TZ),
            "created_by": 123,
            "template_id": None,
        }
    ]
    assert message.replies
    assert "Ок, напомню" in message.replies[0][0]
    assert "Алиаса" not in message.replies[0][0]


def test_remind_nested_en_remind_evening_realistic_path(main_module, monkeypatch):
    created = _capture_add_reminder(main_module, monkeypatch)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 17, 30, tzinfo=TZ))

    update, context, message = _mk_private("/remind remind tomorrow evening buy milk")

    asyncio.run(main_module.remind_command(update, context))

    assert created == [
        {
            "chat_id": 456,
            "text": "buy milk",
            "remind_at": datetime(2026, 6, 13, 18, 0, tzinfo=TZ),
            "created_by": 123,
            "template_id": None,
        }
    ]
    assert message.replies
    assert "Ок, напомню" in message.replies[0][0]
    assert "Алиаса" not in message.replies[0][0]


def test_remind_ru_evening_without_nested_prefix_realistic_path(main_module, monkeypatch):
    created = _capture_add_reminder(main_module, monkeypatch)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 17, 30, tzinfo=TZ))

    update, context, message = _mk_private("/remind завтра вечером купить молоко")

    asyncio.run(main_module.remind_command(update, context))

    assert created == [
        {
            "chat_id": 456,
            "text": "купить молоко",
            "remind_at": datetime(2026, 6, 13, 18, 0, tzinfo=TZ),
            "created_by": 123,
            "template_id": None,
        }
    ]
    assert message.replies
    assert "Ок, напомню" in message.replies[0][0]


def test_remind_relative_week_realistic_path(main_module, monkeypatch):
    created = _capture_add_reminder(main_module, monkeypatch)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 17, 30, tzinfo=TZ))

    update, context, message = _mk_private("/remind через неделю - написать в цветы")

    asyncio.run(main_module.remind_command(update, context))

    assert created == [
        {
            "chat_id": 456,
            "text": "написать в цветы",
            "remind_at": datetime(2026, 6, 19, 17, 30, tzinfo=TZ),
            "created_by": 123,
            "template_id": None,
        }
    ]
    assert message.replies
    assert "Ок, напомню" in message.replies[0][0]


def test_remind_next_wednesday_realistic_path(main_module, monkeypatch):
    created = _capture_add_reminder(main_module, monkeypatch)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 17, 30, tzinfo=TZ))

    update, context, message = _mk_private("/remind в следующую среду - проверить документы")

    asyncio.run(main_module.remind_command(update, context))

    assert created == [
        {
            "chat_id": 456,
            "text": "проверить документы",
            "remind_at": datetime(2026, 6, 17, 11, 0, tzinfo=TZ),
            "created_by": 123,
            "template_id": None,
        }
    ]
    assert message.replies
    assert "Ок, напомню" in message.replies[0][0]


def test_remind_unknown_alias_still_errors_realistic_path(main_module, monkeypatch):
    created = _capture_add_reminder(main_module, monkeypatch)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 17, 30, tzinfo=TZ))

    update, context, message = _mk_private("/remind абракадабраалиас завтра 18:00 - тест")

    asyncio.run(main_module.remind_command(update, context))

    assert created == []
    assert len(message.replies) == 1
    assert 'Алиаса "абракадабраалиас" не существует' in message.replies[0][0]
