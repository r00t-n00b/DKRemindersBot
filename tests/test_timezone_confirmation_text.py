import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from single_oneoff_reminder import handle_single_oneoff_reminder


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


async def _noop_gemini(*args, **kwargs):
    return "NO_REMINDER"


def test_oneoff_confirmation_uses_author_timezone_label():
    message = FakeMessage()

    async def safe_reply(message_obj, text, **kwargs):
        await message_obj.reply_text(text, **kwargs)

    asyncio.run(
        handle_single_oneoff_reminder(
            raw_single="через 5 минут тест Москв",
            now=datetime(2026, 6, 29, 17, 33, tzinfo=ZoneInfo("Europe/Moscow")),
            target_chat_id=100,
            used_alias=None,
            chat=SimpleNamespace(id=100, type="private"),
            user=SimpleNamespace(id=42),
            message=message,
            default_time=None,
            private_chat_type="private",
            parse_with_optional_default_time=lambda parser, raw, now, default_time=None: (
                datetime(2026, 6, 29, 16, 38, tzinfo=ZoneInfo("Europe/Madrid")),
                "тест Москв",
            ),
            parse_date_time_smart=lambda *args, **kwargs: None,
            normalize_plain_text_reminder_with_gemini=_noop_gemini,
            normalize_gemini_reminder_command_text=lambda text: text,
            normalize_reminder_text_fallback=lambda text: text,
            add_reminder=lambda **kwargs: 123,
            build_created_reminder_actions_keyboard=lambda reminder_id: None,
            format_created_reminder_text=lambda when_str, reminder_text: f"Ок, напомню {when_str}: {reminder_text}",
            msg_parse_date_text_failed="Не понял дату",
            safe_reply=safe_reply,
            logger=SimpleNamespace(info=lambda *args, **kwargs: None),
        )
    )

    assert message.replies == [("Ок, напомню 29.06 17:38 Россия / Москва: тест Москв", {"reply_markup": None})]
