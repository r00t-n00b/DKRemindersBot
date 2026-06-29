import asyncio
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def plain_text_tests_have_timezone(main_module, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_user_timezone_name_raw",
        lambda user_id: "Europe/Madrid",
        raising=False,
    )


class DummyMessage:
    def __init__(self, text):
        self.text = text
        self.voice = None
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def _mk_update(text, chat_type="private", user_id=123, chat_id=456):
    message = DummyMessage(text)
    chat = SimpleNamespace(id=chat_id, type=chat_type)
    user = SimpleNamespace(id=user_id, username="u", first_name="U", last_name="L")
    update = SimpleNamespace(
        effective_chat=chat,
        effective_message=message,
        effective_user=user,
        message=message,
    )
    context = SimpleNamespace(args=[], user_data={})
    return update, context, message


def test_plain_text_reminder_ignores_group_chat(main_module, monkeypatch):
    called = False

    async def fake_normalize(*args, **kwargs):
        nonlocal called
        called = True
        return "завтра 18:00 - test"

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)

    update, context, message = _mk_update(
        "напомни завтра в 18 test",
        chat_type="group",
    )

    asyncio.run(main_module.plain_text_remind_command(update, context))

    assert called is False
    assert message.replies == []


def test_plain_text_reminder_ignores_slash_commands(main_module, monkeypatch):
    called = False

    async def fake_normalize(*args, **kwargs):
        nonlocal called
        called = True
        return "завтра 18:00 - test"

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)

    update, context, message = _mk_update("/help")

    asyncio.run(main_module.plain_text_remind_command(update, context))

    assert called is False
    assert message.replies == []


def test_plain_text_reminder_no_reminder_replies_with_help(main_module, monkeypatch):
    async def fake_normalize(text, created_by):
        assert text == "просто болтовня"
        assert created_by == 123
        return "NO_REMINDER"

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)

    update, context, message = _mk_update("просто болтовня")

    asyncio.run(main_module.plain_text_remind_command(update, context))

    assert len(message.replies) == 1
    reply, _ = message.replies[0]
    assert "Я не понял, нужно ли здесь поставить напоминание" in reply
    assert "/remind завтра 18:00 - поздравить Саню" in reply
    assert "напомни завтра в 18:00 поздравить Саню" in reply


def test_plain_text_reminder_normalized_remind_is_proxied_to_remind_command(main_module, monkeypatch):
    seen = {}

    async def fake_normalize(text, created_by):
        assert text == "напомни завтра поздравить Саню"
        assert created_by == 123
        return "/remind завтра 18:00 - поздравить Саню"

    async def fake_remind_command(update, context):
        seen["text"] = update.effective_message.text
        await update.effective_message.reply_text("Ок, напомню")

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    update, context, message = _mk_update("напомни завтра поздравить Саню")

    asyncio.run(main_module.plain_text_remind_command(update, context))

    assert seen["text"] == "/remind завтра 18:00 - поздравить Саню"
    assert len(message.replies) == 1

    reply, _ = message.replies[0]
    assert "Я понял:" in reply
    assert "завтра 18:00 - поздравить Саню" in reply
    assert "Ок, напомню" in reply


def test_plain_text_reminder_applies_gemini_interval_normalization_before_proxy(main_module, monkeypatch):
    seen = {}

    async def fake_normalize(text, created_by):
        return "каждые полтора часа - попить воды"

    async def fake_remind_command(update, context):
        seen["text"] = update.effective_message.text
        await update.effective_message.reply_text("Ок, напомню")

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    update, context, message = _mk_update("напоминай каждые полтора часа попить воды")

    asyncio.run(main_module.plain_text_remind_command(update, context))

    assert seen["text"] == "/remind every 90 minutes - попить воды"

    reply, _ = message.replies[0]
    assert "Я понял:" in reply
    assert "every 90 minutes - попить воды" in reply


def test_plain_text_reminder_falls_back_when_gemini_fails(main_module, monkeypatch):
    seen = {}

    async def fake_normalize(text, created_by):
        raise RuntimeError("gemini unavailable")

    async def fake_remind_command(update, context):
        seen["text"] = update.effective_message.text
        await update.effective_message.reply_text("Ок, напомню")

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fake_normalize)
    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    update, context, message = _mk_update("напомни завтра в 18:00 купить молоко")

    asyncio.run(main_module.plain_text_remind_command(update, context))

    assert seen["text"] == "/remind завтра 18:00 - купить молоко"

    reply, _ = message.replies[0]
    assert "Я понял:" in reply
    assert "завтра 18:00 - купить молоко" in reply
    assert "Ок, напомню" in reply


def test_plain_text_russian_month_name_uses_local_normalizer_without_gemini(main_module, monkeypatch):
    seen = {}

    async def fail_normalize(*args, **kwargs):
        raise AssertionError("Gemini must not be called for explicit Russian month-name date")

    async def fake_remind_command(update, context):
        seen["text"] = update.effective_message.text
        await update.effective_message.reply_text("Ок, напомню")

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fail_normalize)
    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    update, context, message = _mk_update(
        "напомни 1 октября пересчитать стоимость начинки квартиры и поменять в страховке"
    )

    asyncio.run(main_module.plain_text_remind_command(update, context))

    assert seen["text"] == (
        "/remind 1 октября - пересчитать стоимость начинки квартиры и поменять в страховке"
    )

    assert len(message.replies) == 1
    reply, _ = message.replies[0]
    assert "Я понял:" in reply
    assert "1 октября - пересчитать стоимость начинки квартиры и поменять в страховке" in reply
    assert "Ок, напомню" in reply


def test_plain_text_relative_day_with_explicit_time_uses_local_normalizer_without_gemini(main_module, monkeypatch):
    seen = {}

    async def fail_normalize(*args, **kwargs):
        raise AssertionError("Gemini must not be called for explicit relative-day time")

    async def fake_remind_command(update, context):
        seen["text"] = update.effective_message.text
        await update.effective_message.reply_text("Ок, напомню")

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fail_normalize)
    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    update, context, message = _mk_update("напомни завтра в 18:00 купить молоко")

    asyncio.run(main_module.plain_text_remind_command(update, context))

    assert seen["text"] == "/remind завтра 18:00 - купить молоко"

    assert len(message.replies) == 1
    reply, _ = message.replies[0]
    assert "Я понял:" in reply
    assert "завтра 18:00 - купить молоко" in reply
    assert "Ок, напомню" in reply


def test_plain_text_relative_minute_reminder_uses_local_normalizer(main_module):
    m = main_module

    assert (
        m._normalize_plain_text_relative_reminder_locally("напомни через минуту тест")
        == "in 1 minute - тест"
    )
    assert (
        m._normalize_plain_text_relative_reminder_locally("напомни через 5 минут тест")
        == "in 5 minutes - тест"
    )
    assert (
        m._normalize_plain_text_relative_reminder_locally("напомни через час тест")
        == "in 1 hour - тест"
    )
    assert (
        m._normalize_plain_text_relative_reminder_locally("напомни через 2 часа тест")
        == "in 2 hours - тест"
    )


def test_plain_text_relative_english_reminder_uses_local_normalizer(main_module):
    m = main_module

    assert (
        m._normalize_plain_text_relative_reminder_locally("remind me in a minute test")
        == "in 1 minute - test"
    )
    assert (
        m._normalize_plain_text_relative_reminder_locally("remind me in 10 minutes test")
        == "in 10 minutes - test"
    )
    assert (
        m._normalize_plain_text_relative_reminder_locally("remind me in an hour test")
        == "in 1 hour - test"
    )


def test_plain_text_relative_local_normalizer_uses_singular_forms(main_module):
    m = main_module

    assert (
        m._normalize_plain_text_relative_reminder_locally("напомни через минуту тест")
        == "in 1 minute - тест"
    )
    assert (
        m._normalize_plain_text_relative_reminder_locally("напомни через 5 минут тест")
        == "in 5 minutes - тест"
    )
    assert (
        m._normalize_plain_text_relative_reminder_locally("напомни через час тест")
        == "in 1 hour - тест"
    )
    assert (
        m._normalize_plain_text_relative_reminder_locally("напомни через 2 часа тест")
        == "in 2 hours - тест"
    )


def test_plain_text_relative_local_normalizer_does_not_call_gemini(main_module, monkeypatch):
    seen = {}

    async def fail_normalize(*args, **kwargs):
        raise AssertionError("Gemini must not be called for simple relative reminders")

    async def fake_remind_command(update, context):
        seen["text"] = update.effective_message.text
        await update.effective_message.reply_text("Ок, напомню")

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fail_normalize)
    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    update, context, message = _mk_update("напомни через минуту тест")

    asyncio.run(main_module.plain_text_remind_command(update, context))

    assert seen["text"] == "/remind in 1 minute - тест"
    reply, _ = message.replies[0]
    assert "Я понял:" in reply
    assert "in 1 minute - тест" in reply


def test_linkchat_and_alias_examples_include_natural_language(main_module):
    import messages

    message = messages.msg_linkchat_success("football")

    assert "напомни football 28.11 12:00 завтра футбол" in message
    assert "/remind football 28.11 12:00 - завтра футбол" in message
