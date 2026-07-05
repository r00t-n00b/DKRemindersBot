import asyncio
from types import SimpleNamespace

import dkreminders_bot.commands.plain_text_remind_deps as plain_text_remind_deps
import dkreminders_bot.commands.plain_text_remind_flow as plain_text_remind_flow


class FakeChat:
    PRIVATE = "private"


class FakeMessage:
    def __init__(self, text):
        self.text = text


async def fake_safe_reply(message, text, **kwargs):
    fake_safe_reply.calls.append((text, kwargs))


async def fake_remind_command(update, context):
    fake_remind_command.calls.append(update.effective_message.text)


def test_plain_text_without_timezone_shows_picker_and_does_not_create_reminder():
    fake_safe_reply.calls = []
    fake_remind_command.calls = []

    namespace = {
        "Chat": FakeChat,
        "MSG_NOT_UNDERSTOOD_PLAIN_TEXT": "not understood",
        "NormalizedReminderMessageProxy": lambda message, text, normalized: SimpleNamespace(text=text, normalized=normalized),
        "SimpleNamespace": SimpleNamespace,
        "_normalize_plain_text_relative_reminder_locally": lambda raw: None,
        "_normalize_plain_text_reminder_locally": lambda raw: "30.06 10:00 - тест",
        "_normalize_reminder_text_fallback": lambda raw: raw,
        "logger": SimpleNamespace(info=lambda *a, **k: None, exception=lambda *a, **k: None),
        "normalize_gemini_reminder_command_text": lambda text: text,
        "normalize_plain_text_reminder_with_gemini": lambda raw, user_id: "30.06 10:00 - тест",
        "remind_command": fake_remind_command,
        "safe_reply": fake_safe_reply,
        "type": type,
        "get_user_timezone_name_raw": lambda user_id: None,
        "build_first_timezone_prompt": lambda: "Telegram не передаёт мне твой часовой пояс автоматически",
        "build_timezone_picker_keyboard": lambda: "timezone-picker",
    }
    deps = plain_text_remind_deps.build_plain_text_remind_command_deps(namespace)

    message = FakeMessage("напомни завтра тест")
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="private", id=100),
        effective_message=message,
        effective_user=SimpleNamespace(id=555),
        message=message,
    )

    context = SimpleNamespace(user_data={})

    asyncio.run(plain_text_remind_flow.handle_plain_text_remind_command(update, context, deps))

    assert fake_remind_command.calls == []
    assert context.user_data["pending_plain_text_reminder_after_timezone"] == "напомни завтра тест"
    assert fake_safe_reply.calls == [("Telegram не передаёт мне твой часовой пояс автоматически", {"reply_markup": "timezone-picker"})]

def test_timezone_settings_deps_can_resume_pending_plain_text(main_module):
    deps = main_module._build_timezone_settings_deps()

    assert deps.get_user_timezone_name_raw is main_module.get_user_timezone_name_raw
    assert deps.plain_text_remind_command is main_module.plain_text_remind_command

