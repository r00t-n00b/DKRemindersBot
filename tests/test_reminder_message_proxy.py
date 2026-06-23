import asyncio

import main
from reminder_message_proxy import NormalizedReminderMessageProxy


class OriginalMessage:
    def __init__(self):
        self.voice = object()
        self.chat_id = 123
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def test_normalized_reminder_message_proxy_exposes_command_text_and_original_attrs():
    original = OriginalMessage()
    proxy = NormalizedReminderMessageProxy(
        original,
        "/remind завтра 10:00 - купить молоко",
        "завтра 10:00 - купить молоко",
    )

    assert proxy.text == "/remind завтра 10:00 - купить молоко"
    assert proxy.normalized_text == "завтра 10:00 - купить молоко"
    assert proxy.voice is original.voice
    assert proxy.chat_id == 123


def test_normalized_reminder_message_proxy_prefixes_reply_with_normalized_text():
    async def run():
        original = OriginalMessage()
        proxy = NormalizedReminderMessageProxy(
            original,
            "/remind завтра 10:00 - купить молоко",
            "завтра 10:00 - купить молоко",
        )

        await proxy.reply_text("Создал напоминание", reply_markup="markup")

        assert original.replies == [
            (
                "Я понял:\n"
                "завтра 10:00 - купить молоко\n\n"
                "Создал напоминание",
                {"reply_markup": "markup"},
            )
        ]

    asyncio.run(run())


def test_main_reexports_normalized_reminder_message_proxy_for_handlers():
    assert main.NormalizedReminderMessageProxy is NormalizedReminderMessageProxy


def test_old_inner_proxy_classes_are_removed_from_main_source():
    from pathlib import Path

    source = Path("main.py").read_text()

    assert "class VoiceReminderMessageProxy" not in source
    assert "class PlainTextReminderMessageProxy" not in source
    assert source.count("NormalizedReminderMessageProxy(") >= 2
    assert "from reminder_message_proxy import NormalizedReminderMessageProxy" in source
