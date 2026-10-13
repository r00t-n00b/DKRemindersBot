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
    import dkreminders_bot.ui.messages as messages

    message = messages.msg_linkchat_success("football")

    assert "напомни football 28.11 12:00 завтра футбол" in message
    assert "/remind football 28.11 12:00 - завтра футбол" in message


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        ("напомни в 13.46 рейд", "/remind 13:46 - рейд"),
        ("напомни 13:46 рейд", "/remind 13:46 - рейд"),
        ("напомни в 13 рейд", "/remind 13:00 - рейд"),
        ("напомни завтра 13.46 рейд", "/remind завтра 13:46 - рейд"),
        ("напомни сегодня в 13 рейд", "/remind сегодня 13:00 - рейд"),
        ("напомни в понедельник 22.58 спросить", "/remind в понедельник 22:58 - спросить"),
        ("напомни 1 октября в 13.46 страховка", "/remind 1 октября в 13:46 - страховка"),
        ("remind me at 13.46 raid", "/remind 13:46 - raid"),
        ("remind me tomorrow at 13.46 raid", "/remind tomorrow 13:46 - raid"),
        ("remind me 29 may at 18.46 ask", "/remind 29 may 18:46 - ask"),
    ],
)
def test_plain_text_explicit_time_patterns_use_local_normalizer_without_gemini(
    main_module,
    monkeypatch,
    raw_text,
    expected,
):
    seen = {}

    async def fail_normalize(*args, **kwargs):
        raise AssertionError("Gemini must not be called for explicit local time patterns")

    async def fake_remind_command(update, context):
        seen["text"] = update.effective_message.text
        await update.effective_message.reply_text("Ок, напомню")

    monkeypatch.setattr(main_module, "normalize_plain_text_reminder_with_gemini", fail_normalize)
    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    update, context, message = _mk_update(raw_text)

    asyncio.run(main_module.plain_text_remind_command(update, context))

    assert seen["text"] == expected
    reply, _ = message.replies[0]
    assert "Я понял:" in reply
    assert expected.removeprefix("/remind ") in reply


def test_plain_text_fallback_understands_dot_time_when_gemini_fails(main_module):
    assert (
        main_module._normalize_reminder_text_fallback("напомни в 13.46 рейд")
        == "13:46 - рейд"
    )


@pytest.mark.asyncio
async def test_reply_context_without_reply_asks_user_to_reply_and_skips_gemini(main_module, monkeypatch):
    update, context, message = _mk_update("напомни через полчаса об этом")
    message.reply_to_message = None

    gemini_called = False

    async def fake_gemini(*args, **kwargs):
        nonlocal gemini_called
        gemini_called = True
        return "unexpected"

    monkeypatch.setattr(
        main_module,
        "normalize_plain_text_reminder_with_gemini",
        fake_gemini,
    )

    await main_module.plain_text_remind_command(update, context)

    assert gemini_called is False
    assert message.replies == []
    assert context.user_data["pending_forward_comment_reminder"]["raw_text"] == "напомни через полчаса об этом"
    assert context.user_data["pending_forward_comment_reminder"]["command_message"] is message


@pytest.mark.asyncio
async def test_reply_context_text_is_used_by_real_plain_text_flow(main_module, monkeypatch):
    update, context, message = _mk_update("напомни через полчаса об этом")

    source = SimpleNamespace(
        text="заказать соль",
        message_id=77,
        chat=SimpleNamespace(id=update.effective_chat.id),
    )
    message.reply_to_message = source

    seen = {}

    async def fake_remind_command(proxy_update, proxy_context):
        seen["text"] = proxy_update.effective_message.text
        seen["reply_to_message"] = proxy_update.effective_message.reply_to_message

    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    await main_module.plain_text_remind_command(update, context)

    assert seen["text"] == "/remind через полчаса - заказать соль"
    assert seen["reply_to_message"] is source


@pytest.mark.asyncio
async def test_reply_context_document_caption_is_used_by_real_plain_text_flow(main_module, monkeypatch):
    update, context, message = _mk_update(
        "напомни через полчаса про это сообщение"
    )

    source = SimpleNamespace(
        text=None,
        caption="Tab 1 их, Tab 2 мой",
        document=SimpleNamespace(file_name="PMM PLG July 2026.pdf"),
        message_id=88,
        chat=SimpleNamespace(id=update.effective_chat.id),
    )
    message.reply_to_message = source

    seen = {}

    async def fake_remind_command(proxy_update, proxy_context):
        seen["text"] = proxy_update.effective_message.text

    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    await main_module.plain_text_remind_command(update, context)

    assert seen["text"] == (
        "/remind через полчаса - "
        "PMM PLG July 2026.pdf: Tab 1 их, Tab 2 мой"
    )


@pytest.mark.asyncio
async def test_incomplete_plain_text_reminder_waits_for_forward(main_module, monkeypatch):
    update, context, message = _mk_update("напомни через полчаса")

    monkeypatch.setattr(
        main_module,
        "_normalize_plain_text_reminder_locally",
        lambda raw: "через полчаса - ",
    )

    called = False

    async def fake_remind_command(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    await main_module.plain_text_remind_command(update, context)

    assert called is False
    assert message.replies == []
    assert context.user_data["pending_forward_comment_reminder"]["raw_text"] == "напомни через полчаса"


@pytest.mark.asyncio
async def test_complete_plain_text_reminder_does_not_wait_for_forward(main_module, monkeypatch):
    update, context, message = _mk_update("напомни через полчаса купить соль")

    seen = {}

    async def fake_remind_command(proxy_update, proxy_context):
        seen["text"] = proxy_update.effective_message.text

    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    await main_module.plain_text_remind_command(update, context)

    assert seen["text"] == "/remind через полчаса - купить соль"
    assert "pending_forward_comment_reminder" not in context.user_data
import pytest
from types import SimpleNamespace


@pytest.mark.asyncio
async def test_forward_handler_adds_implicit_context_phrase(main_module, monkeypatch):
    command_message = SimpleNamespace(
        text="напомни через полчаса",
        reply_to_message=None,
    )
    forwarded = SimpleNamespace(
        message_id=904,
        chat=SimpleNamespace(id=123),
        text="запости стол и стул в меркадо",
        caption=None,
        document=None,
        photo=None,
        video=None,
        voice=None,
        audio=None,
        animation=None,
        sticker=None,
        forward_origin=SimpleNamespace(
            sender_user_name="Dmitriy",
            sender_user=None,
        ),
    )

    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=123, type=main_module.Chat.PRIVATE),
        effective_message=forwarded,
        effective_user=SimpleNamespace(id=456),
    )
    context = SimpleNamespace(
        user_data={
            "pending_forward_comment_reminder": {
                "raw_text": "напомни через полчаса",
                "command_message": command_message,
            }
        }
    )

    seen = {}

    async def fake_plain_text(proxy_update, proxy_context):
        seen["text"] = proxy_update.effective_message.text
        seen["reply"] = proxy_update.effective_message.reply_to_message

    monkeypatch.setattr(main_module, "plain_text_remind_command", fake_plain_text)

    await main_module.forwarded_reminder_context_message(update, context)

    assert seen["text"] == "напомни через полчаса об этом"
    assert seen["reply"] is forwarded
    assert "pending_forward_comment_reminder" not in context.user_data


@pytest.mark.asyncio
async def test_reply_context_suppresses_normalized_prefix(main_module, monkeypatch):
    update, context, message = _mk_update("напомни через полчаса об этом")

    source = SimpleNamespace(
        text="заказать соль",
        message_id=77,
        chat=SimpleNamespace(id=update.effective_chat.id),
    )
    message.reply_to_message = source

    seen = {}

    async def fake_remind_command(proxy_update, proxy_context):
        proxy_message = proxy_update.effective_message
        seen["suppress"] = proxy_message.suppress_normalized_prefix
        await proxy_message.reply_text("Ок, напомню")

    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    await main_module.plain_text_remind_command(update, context)

    assert seen["suppress"] is True
    assert message.replies == [("Ок, напомню", {})]


@pytest.mark.asyncio
async def test_regular_plain_text_keeps_normalized_prefix(main_module, monkeypatch):
    update, context, message = _mk_update("напомни через минуту купить соль")

    seen = {}

    async def fake_remind_command(proxy_update, proxy_context):
        proxy_message = proxy_update.effective_message
        seen["suppress"] = proxy_message.suppress_normalized_prefix
        await proxy_message.reply_text("Ок, напомню")

    monkeypatch.setattr(main_module, "remind_command", fake_remind_command)

    await main_module.plain_text_remind_command(update, context)

    assert seen["suppress"] is False
    assert len(message.replies) == 1
    assert "Я понял:" in message.replies[0][0]
    assert "Ок, напомню" in message.replies[0][0]
