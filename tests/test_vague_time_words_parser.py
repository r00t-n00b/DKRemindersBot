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


def test_parse_ru_tomorrow_evening_removes_time_word_from_text(main_module):
    now = datetime(2026, 6, 12, 17, 30, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "завтра вечером купить молоко",
        now,
    )

    assert remind_at == datetime(2026, 6, 13, 18, 0, tzinfo=TZ)
    assert text == "купить молоко"


def test_parse_en_tomorrow_evening_removes_time_word_from_text(main_module):
    now = datetime(2026, 6, 12, 17, 30, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "tomorrow evening buy milk",
        now,
    )

    assert remind_at == datetime(2026, 6, 13, 18, 0, tzinfo=TZ)
    assert text == "buy milk"


def test_remind_nested_prefix_tomorrow_evening_uses_18_00_without_alias(main_module, monkeypatch):
    created = []

    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 17, 30, tzinfo=TZ))
    monkeypatch.setattr(
        main_module,
        "add_reminder",
        lambda chat_id, text, remind_at, created_by=None, template_id=None: created.append(
            {
                "chat_id": chat_id,
                "text": text,
                "remind_at": remind_at,
                "created_by": created_by,
                "template_id": template_id,
            }
        ) or 777,
    )

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
