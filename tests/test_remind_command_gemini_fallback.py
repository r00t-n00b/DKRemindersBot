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


def test_remind_strict_parse_success_does_not_call_gemini(main_module, monkeypatch):
    called = False
    created = []

    async def fake_normalize(*args, **kwargs):
        nonlocal called
        called = True
        return "завтра 18:00 - should not happen"

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 10, 0, tzinfo=TZ))
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

    update, context, message = _mk_private("/remind завтра 18:00 - купить молоко")

    asyncio.run(main_module.remind_command(update, context))

    assert called is False
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


def test_remind_strict_parse_failure_uses_gemini_normalized_text(main_module, monkeypatch):
    created = []
    calls = []
    real_parse = main_module.parse_date_time_smart

    def fake_parse(raw, now):
        if raw == "свободная фраза без даты":
            raise ValueError("forced strict parse failure")
        return real_parse(raw, now)

    async def fake_normalize(text, created_by):
        calls.append((text, created_by))
        return "завтра 18:00 - купить молоко"

    monkeypatch.setattr(main_module, "parse_date_time_smart", fake_parse)
    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 10, 0, tzinfo=TZ))
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

    update, context, message = _mk_private("/remind свободная фраза без даты")

    asyncio.run(main_module.remind_command(update, context))

    assert calls == [("свободная фраза без даты", 123)]
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

def test_remind_gemini_fallback_accepts_slash_remind_prefix(main_module, monkeypatch):
    created = []
    real_parse = main_module.parse_date_time_smart

    def fake_parse(raw, now):
        if raw == "свободная фраза без даты":
            raise ValueError("forced strict parse failure")
        return real_parse(raw, now)

    async def fake_normalize(text, created_by):
        return "/remind завтра 18:00 - купить молоко"

    monkeypatch.setattr(main_module, "parse_date_time_smart", fake_parse)
    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 10, 0, tzinfo=TZ))
    monkeypatch.setattr(
        main_module,
        "add_reminder",
        lambda chat_id, text, remind_at, created_by=None, template_id=None: created.append(text) or 777,
    )

    update, context, message = _mk_private("/remind свободная фраза без даты")

    asyncio.run(main_module.remind_command(update, context))

    assert created == ["купить молоко"]
    assert message.replies
    assert "Ок, напомню" in message.replies[0][0]


def test_remind_gemini_fallback_no_reminder_keeps_old_error(main_module, monkeypatch):
    async def fake_normalize(text, created_by):
        return "NO_REMINDER"

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 10, 0, tzinfo=TZ))

    update, context, message = _mk_private("/remind просто болтовня")

    asyncio.run(main_module.remind_command(update, context))

    assert len(message.replies) == 1
    assert "Не смог понять дату и текст:" in message.replies[0][0]


def test_remind_gemini_fallback_bad_normalized_text_keeps_old_error(main_module, monkeypatch):
    async def fake_normalize(text, created_by):
        return "тоже непонятно"

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 10, 0, tzinfo=TZ))

    update, context, message = _mk_private("/remind просто болтовня")

    asyncio.run(main_module.remind_command(update, context))

    assert len(message.replies) == 1
    assert "Не смог понять дату и текст:" in message.replies[0][0]


def test_remind_gemini_fallback_exception_keeps_old_error(main_module, monkeypatch):
    async def fake_normalize(text, created_by):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 10, 0, tzinfo=TZ))

    update, context, message = _mk_private("/remind просто болтовня")

    asyncio.run(main_module.remind_command(update, context))

    assert len(message.replies) == 1
    assert "Не смог понять дату и текст:" in message.replies[0][0]


def test_remind_command_strips_nested_remind_word_before_alias_routing(main_module, monkeypatch):
    created = []
    calls = []
    real_parse = main_module.parse_date_time_smart

    def fake_parse(raw, now):
        if raw == "завтра вечером купить молоко":
            raise ValueError("forced strict parse failure")
        return real_parse(raw, now)

    async def fake_normalize(text, created_by):
        calls.append((text, created_by))
        return "завтра 18:00 - купить молоко"

    monkeypatch.setattr(main_module, "parse_date_time_smart", fake_parse)
    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 10, 0, tzinfo=TZ))
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

    assert calls == [("завтра вечером купить молоко", 123)]
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
