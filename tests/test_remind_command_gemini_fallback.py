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
    assert message.replies[0][0] == main_module.MSG_PARSE_DATE_TEXT_FAILED


def test_remind_gemini_fallback_bad_normalized_text_keeps_old_error(main_module, monkeypatch):
    async def fake_normalize(text, created_by):
        return "тоже непонятно"

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 10, 0, tzinfo=TZ))

    update, context, message = _mk_private("/remind просто болтовня")

    asyncio.run(main_module.remind_command(update, context))

    assert len(message.replies) == 1
    assert message.replies[0][0] == main_module.MSG_PARSE_DATE_TEXT_FAILED


def test_remind_gemini_fallback_exception_keeps_old_error(main_module, monkeypatch):
    async def fake_normalize(text, created_by):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 10, 0, tzinfo=TZ))

    update, context, message = _mk_private("/remind просто болтовня")

    asyncio.run(main_module.remind_command(update, context))

    assert len(message.replies) == 1
    assert message.replies[0][0] == main_module.MSG_PARSE_DATE_TEXT_FAILED


def test_remind_command_strips_nested_remind_word_before_alias_routing(main_module, monkeypatch):
    created = []
    calls = []
    real_parse = main_module.parse_date_time_smart

    def fake_user_alias(alias, user_id):
        assert alias != "напомни"
        return None

    def fake_chat_alias(alias, user_id):
        assert alias != "напомни"
        return None

    def fake_parse(raw, now):
        if raw == "завтра вечером купить молоко":
            raise ValueError("forced strict parse failure")
        return real_parse(raw, now)

    async def fake_normalize(text, created_by):
        calls.append((text, created_by))
        return "завтра 18:00 - купить молоко"

    monkeypatch.setattr(main_module, "get_user_alias_chat_id_for_user", fake_user_alias)
    monkeypatch.setattr(main_module, "get_chat_id_by_alias_for_user", fake_chat_alias)
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

def test_remind_gemini_fallback_timeout_keeps_old_error(main_module, monkeypatch):
    real_parse = main_module.parse_date_time_smart
    calls = []

    def fake_parse(raw, now):
        if raw == "gemini hangs forever":
            raise ValueError("forced strict parse failure")
        return real_parse(raw, now)

    async def fake_normalize(text, created_by):
        calls.append((text, created_by))
        await asyncio.sleep(1)
        return "завтра 18:00 - should not happen"

    def fail_add_reminder(*args, **kwargs):
        raise AssertionError("add_reminder must not be called after Gemini timeout")

    monkeypatch.setenv("GEMINI_REMINDER_PARSE_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setattr(main_module, "parse_date_time_smart", fake_parse)
    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "add_reminder", fail_add_reminder)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 12, 10, 0, tzinfo=TZ))

    update, context, message = _mk_private("/remind gemini hangs forever")

    asyncio.run(main_module.remind_command(update, context))

    assert calls == [("gemini hangs forever", 123)]
    assert len(message.replies) == 1
    assert message.replies[0][0] == main_module.MSG_PARSE_DATE_TEXT_FAILED
    assert "forced strict parse failure" not in message.replies[0][0]


def test_invalid_english_monthly_recurring_does_not_call_gemini(main_module, monkeypatch):
    async def fail_normalize(*args, **kwargs):
        raise AssertionError("Gemini fallback must not be called for obvious recurring input")

    def fail_add_reminder(*args, **kwargs):
        raise AssertionError("add_reminder must not be called for invalid recurring input")

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fail_normalize)
    monkeypatch.setattr(main_module, "add_reminder", fail_add_reminder)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 15, 16, 6, tzinfo=TZ))

    update, context, message = _mk_private("/remind on the 35th of every month - новый джонкейк")

    asyncio.run(main_module.remind_command(update, context))

    assert len(message.replies) == 1
    assert message.replies[0][0] == main_module.msg_recurring_parse_failed(is_private=True)
    assert "Gemini fallback must not be called" not in message.replies[0][0]


def test_invalid_russian_monthly_recurring_does_not_call_gemini(main_module, monkeypatch):
    async def fail_normalize(*args, **kwargs):
        raise AssertionError("Gemini fallback must not be called for obvious recurring input")

    def fail_add_reminder(*args, **kwargs):
        raise AssertionError("add_reminder must not be called for invalid recurring input")

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fail_normalize)
    monkeypatch.setattr(main_module, "add_reminder", fail_add_reminder)
    monkeypatch.setattr(main_module, "get_now", lambda: datetime(2026, 6, 15, 16, 6, tzinfo=TZ))

    update, context, message = _mk_private("/remind восьмидесятого числа каждого месяца - первый раз")

    asyncio.run(main_module.remind_command(update, context))

    assert len(message.replies) == 1
    assert message.replies[0][0] == main_module.msg_recurring_parse_failed(is_private=True)

def test_date_parse_failure_uses_human_message(main_module, monkeypatch):
    m = main_module

    async def fail_gemini(*args, **kwargs):
        return "NO_REMINDER"

    monkeypatch.setattr(m, "normalize_plain_text_reminder_with_gemini", fail_gemini)

    update, context, message = _mk_private("/remind nonsense")

    asyncio.run(m.remind_command(update, context))

    assert message.replies
    assert message.replies[0][0] == m.MSG_PARSE_DATE_TEXT_FAILED
    assert "Не понял дату/время" not in message.replies[0][0]
