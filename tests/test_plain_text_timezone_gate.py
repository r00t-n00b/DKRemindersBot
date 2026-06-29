import asyncio
from types import SimpleNamespace

from plain_text_remind_flow import handle_plain_text_remind_command


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def test_plain_text_reminder_asks_timezone_before_first_reminder():
    class Chat:
        PRIVATE = "private"

    message = FakeMessage("напомни завтра в 10 купить молоко")
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=100, type=Chat.PRIVATE),
        effective_message=message,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace()

    deps = SimpleNamespace(
        Chat=Chat,
        MSG_NOT_UNDERSTOOD_PLAIN_TEXT="not understood",
        NormalizedReminderMessageProxy=lambda *args, **kwargs: None,
        SimpleNamespace=SimpleNamespace,
        _normalize_plain_text_relative_reminder_locally=lambda text: (_ for _ in ()).throw(AssertionError("must not normalize")),
        _normalize_plain_text_reminder_locally=lambda text: (_ for _ in ()).throw(AssertionError("must not normalize")),
        _normalize_reminder_text_fallback=lambda text: text,
        logger=SimpleNamespace(info=lambda *args, **kwargs: None, exception=lambda *args, **kwargs: None),
        normalize_gemini_reminder_command_text=lambda text: text,
        normalize_plain_text_reminder_with_gemini=lambda text, user_id: text,
        remind_command=lambda update, context: (_ for _ in ()).throw(AssertionError("must not create reminder")),
        safe_reply=lambda message, text, **kwargs: message.reply_text(text, **kwargs),
        type=type,
        get_user_timezone_name_raw=lambda user_id: None,
        build_first_timezone_prompt=lambda: "timezone prompt",
        build_timezone_picker_keyboard=lambda: "timezone keyboard",
    )

    asyncio.run(handle_plain_text_remind_command(update, context, deps))

    assert message.replies == [("timezone prompt", {"reply_markup": "timezone keyboard"})]
