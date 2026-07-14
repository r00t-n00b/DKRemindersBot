import asyncio
from types import SimpleNamespace

from dkreminders_bot.commands.plain_text_remind_flow import handle_plain_text_remind_command
from dkreminders_bot.integrations.plain_text_gemini_normalization import (
    GeminiTextNormalizationTemporaryError,
)
from dkreminders_bot.ui.messages import MSG_PLAIN_TEXT_AI_TEMPORARY_FAILURE


class FakeChat:
    PRIVATE = "private"

    def __init__(self):
        self.id = 100
        self.type = self.PRIVATE


class FakeMessage:
    def __init__(self, text):
        self.text = text


async def _safe_reply(message, text, **kwargs):
    message.replies.append(text)


def test_plain_text_temporary_gemini_failure_is_not_not_understood():
    message = FakeMessage("напомни что-нибудь сложное")
    message.replies = []

    update = SimpleNamespace(
        effective_chat=FakeChat(),
        effective_message=message,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(user_data={})

    async def fail_gemini(raw_text, user_id):
        raise GeminiTextNormalizationTemporaryError("timeout/503")

    def fail_fallback(raw_text):
        raise AssertionError("fallback must not run for temporary Gemini failure")

    async def fail_remind_command(update, context):
        raise AssertionError("remind_command must not run for temporary Gemini failure")

    deps = SimpleNamespace(
        Chat=FakeChat,
        MSG_NOT_UNDERSTOOD_PLAIN_TEXT="Я не понял",
        MSG_PLAIN_TEXT_AI_TEMPORARY_FAILURE=MSG_PLAIN_TEXT_AI_TEMPORARY_FAILURE,
        NormalizedReminderMessageProxy=object,
        SimpleNamespace=SimpleNamespace,
        _normalize_plain_text_relative_reminder_locally=lambda raw_text: None,
        _normalize_plain_text_reminder_locally=lambda raw_text: None,
        _normalize_reminder_text_fallback=fail_fallback,
        logger=SimpleNamespace(
            warning=lambda *args, **kwargs: None,
            exception=lambda *args, **kwargs: None,
            info=lambda *args, **kwargs: None,
        ),
        normalize_gemini_reminder_command_text=lambda text: text,
        normalize_plain_text_reminder_with_gemini=fail_gemini,
        remind_command=fail_remind_command,
        safe_reply=_safe_reply,
        type=type,
    )

    asyncio.run(handle_plain_text_remind_command(update, context, deps))

    assert message.replies == [MSG_PLAIN_TEXT_AI_TEMPORARY_FAILURE]
    assert "Я не понял" not in message.replies[0]
    assert "попробуй" in message.replies[0].lower()
