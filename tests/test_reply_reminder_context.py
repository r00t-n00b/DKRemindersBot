import pytest
from types import SimpleNamespace

from dkreminders_bot.commands.reply_reminder_context import (
    extract_reply_reminder_context,
    refers_to_reply_context,
    replace_reply_context_reference,
)


def _command_with_reply(source):
    return SimpleNamespace(reply_to_message=source)


def test_detects_reply_context_phrases():
    assert refers_to_reply_context("напомни об этом")
    assert refers_to_reply_context("напомни про это сообщение")
    assert refers_to_reply_context("напомни через полчаса об этом сообщении")
    assert not refers_to_reply_context("напомни купить соль")


def test_text_reply():
    source = SimpleNamespace(
        text="заказать соль",
        message_id=77,
        chat=SimpleNamespace(id=123),
    )

    result = extract_reply_reminder_context(_command_with_reply(source))

    assert result.text == "заказать соль"
    assert result.source_message_id == 77
    assert result.source_chat_id == 123


def test_document_with_caption():
    source = SimpleNamespace(
        text=None,
        caption="Tab 1 их, Tab 2 мой",
        document=SimpleNamespace(file_name="PMM PLG July 2026.pdf"),
        message_id=88,
        chat=SimpleNamespace(id=123),
    )

    result = extract_reply_reminder_context(_command_with_reply(source))

    assert result.text == "PMM PLG July 2026.pdf: Tab 1 их, Tab 2 мой"


def test_document_without_caption():
    source = SimpleNamespace(
        text=None,
        caption=None,
        document=SimpleNamespace(file_name="contract.pdf"),
        message_id=89,
        chat=SimpleNamespace(id=123),
    )

    result = extract_reply_reminder_context(_command_with_reply(source))

    assert result.text == "contract.pdf"


def test_forwarded_document_includes_sender():
    source = SimpleNamespace(
        text=None,
        caption=None,
        document=SimpleNamespace(file_name="offer.pdf"),
        forward_origin=SimpleNamespace(
            sender_user_name="Natalia",
            sender_user=None,
        ),
        message_id=90,
        chat=SimpleNamespace(id=123),
    )

    result = extract_reply_reminder_context(_command_with_reply(source))

    assert result.text == "offer.pdf от Natalia"


def test_no_reply():
    assert extract_reply_reminder_context(
        SimpleNamespace(reply_to_message=None)
    ) is None


def test_media_fallbacks():
    source = SimpleNamespace(
        text=None,
        caption=None,
        document=None,
        photo=[object()],
        message_id=91,
        chat=SimpleNamespace(id=123),
    )

    result = extract_reply_reminder_context(_command_with_reply(source))

    assert result.text == "фото"


def test_replacement_prefers_full_phrase():
    assert replace_reply_context_reference(
        "напомни через полчаса про это сообщение",
        "заказать соль",
    ) == "напомни через полчаса заказать соль"

    assert replace_reply_context_reference(
        "напомни об этом сообщении",
        "проверить документ",
    ) == "напомни проверить документ"


def test_main_add_reminder_proxy_forwards_source_relation(main_module, monkeypatch):
    from datetime import datetime, timezone

    seen = {}

    def fake_add_reminder_impl(
        chat_id,
        text,
        remind_at,
        created_by,
        template_id=None,
        *,
        deps,
        timezone_name=None,
        source_chat_id=None,
        source_message_id=None,
    ):
        seen.update(
            chat_id=chat_id,
            text=text,
            created_by=created_by,
            template_id=template_id,
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
        )
        return 999

    monkeypatch.setattr(main_module, "add_reminder_impl", fake_add_reminder_impl)
    monkeypatch.setattr(
        main_module,
        "_timezone_for_created_by",
        lambda created_by: "Europe/Madrid",
    )

    reminder_id = main_module.add_reminder(
        456,
        "проверить документ",
        datetime.now(timezone.utc),
        123,
        source_chat_id=456,
        source_message_id=77,
    )

    assert reminder_id == 999
    assert seen["source_chat_id"] == 456
    assert seen["source_message_id"] == 77


@pytest.mark.asyncio
async def test_real_oneoff_persists_reply_source_relation():
    from datetime import datetime, timezone

    from dkreminders_bot.commands.single_oneoff_reminder import (
        handle_single_oneoff_reminder,
    )

    source = SimpleNamespace(
        message_id=77,
        chat=SimpleNamespace(id=456),
    )
    message = SimpleNamespace(
        reply_to_message=source,
        chat=SimpleNamespace(id=456),
    )
    chat = SimpleNamespace(id=456, type="private")
    user = SimpleNamespace(id=123)

    seen = {}

    def fake_add_reminder(**kwargs):
        seen.update(kwargs)
        return 999

    async def fake_safe_reply(*args, **kwargs):
        return None

    def fake_parse(*args, **kwargs):
        return datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc), "проверить документ"

    await handle_single_oneoff_reminder(
        raw_single="через час - проверить документ",
        now=datetime(2026, 10, 13, 11, 0, tzinfo=timezone.utc),
        target_chat_id=456,
        used_alias=None,
        chat=chat,
        user=user,
        message=message,
        default_time=None,
        private_chat_type="private",
        parse_with_optional_default_time=fake_parse,
        parse_date_time_smart=lambda *args, **kwargs: None,
        normalize_plain_text_reminder_with_gemini=None,
        normalize_gemini_reminder_command_text=lambda x: x,
        normalize_reminder_text_fallback=lambda x: x,
        add_reminder=fake_add_reminder,
        build_created_reminder_actions_keyboard=lambda reminder_id: None,
        format_created_reminder_text=lambda when, text: text,
        msg_parse_date_text_failed="failed",
        safe_reply=fake_safe_reply,
        logger=SimpleNamespace(info=lambda *args, **kwargs: None),
    )

    assert seen["source_chat_id"] == 456
    assert seen["source_message_id"] == 77


@pytest.mark.asyncio
async def test_real_oneoff_without_reply_keeps_old_add_reminder_call_shape():
    from datetime import datetime, timezone

    from dkreminders_bot.commands.single_oneoff_reminder import (
        handle_single_oneoff_reminder,
    )

    message = SimpleNamespace(
        reply_to_message=None,
        chat=SimpleNamespace(id=456),
    )
    chat = SimpleNamespace(id=456, type="private")
    user = SimpleNamespace(id=123)

    seen = {}

    def fake_add_reminder(**kwargs):
        seen.update(kwargs)
        return 999

    async def fake_safe_reply(*args, **kwargs):
        return None

    def fake_parse(*args, **kwargs):
        return datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc), "купить соль"

    await handle_single_oneoff_reminder(
        raw_single="через час - купить соль",
        now=datetime(2026, 10, 13, 11, 0, tzinfo=timezone.utc),
        target_chat_id=456,
        used_alias=None,
        chat=chat,
        user=user,
        message=message,
        default_time=None,
        private_chat_type="private",
        parse_with_optional_default_time=fake_parse,
        parse_date_time_smart=lambda *args, **kwargs: None,
        normalize_plain_text_reminder_with_gemini=None,
        normalize_gemini_reminder_command_text=lambda x: x,
        normalize_reminder_text_fallback=lambda x: x,
        add_reminder=fake_add_reminder,
        build_created_reminder_actions_keyboard=lambda reminder_id: None,
        format_created_reminder_text=lambda when, text: text,
        msg_parse_date_text_failed="failed",
        safe_reply=fake_safe_reply,
        logger=SimpleNamespace(info=lambda *args, **kwargs: None),
    )

    assert set(seen) == {"chat_id", "text", "remind_at", "created_by"}


@pytest.mark.asyncio
async def test_long_reply_context_uses_gemini_summary():
    from dkreminders_bot.commands.reply_reminder_context import summarize_reply_context

    source = "Очень длинный исходный текст. " * 40
    seen = {}

    async def fake_gemini(prompt, created_by):
        seen["prompt"] = prompt
        seen["created_by"] = created_by
        return "посмотреть с Наташей описание вакансии"

    result = await summarize_reply_context(
        source,
        normalize_with_gemini=fake_gemini,
        created_by=123,
    )

    assert result == "посмотреть с Наташей описание вакансии"
    assert seen["created_by"] == 123
    assert source in seen["prompt"]


@pytest.mark.asyncio
async def test_short_reply_context_does_not_call_gemini():
    from dkreminders_bot.commands.reply_reminder_context import summarize_reply_context

    async def fail_gemini(*args, **kwargs):
        raise AssertionError("Gemini must not be called for short reply context")

    result = await summarize_reply_context(
        "заказать соль",
        normalize_with_gemini=fail_gemini,
        created_by=123,
    )

    assert result == "заказать соль"


@pytest.mark.asyncio
async def test_reply_context_gemini_temporary_failure_preserves_source_context():
    from dkreminders_bot.commands.reply_reminder_context import summarize_reply_context

    source = "важный длинный текст " * 50

    class GeminiTextNormalizationTemporaryError(RuntimeError):
        pass

    async def fail_gemini(*args, **kwargs):
        raise GeminiTextNormalizationTemporaryError("503 overloaded")

    result = await summarize_reply_context(
        source,
        normalize_with_gemini=fail_gemini,
        created_by=123,
    )

    assert result
    assert result.startswith("важный длинный текст")
    assert len(result) <= 500


@pytest.mark.asyncio
async def test_long_reply_context_summary_is_capped():
    from dkreminders_bot.commands.reply_reminder_context import summarize_reply_context

    source = "исходный текст " * 100

    async def fake_gemini(*args, **kwargs):
        return "x" * 1000

    result = await summarize_reply_context(
        source,
        normalize_with_gemini=fake_gemini,
        created_by=123,
    )

    assert len(result) == 500
    assert result.endswith("…")
