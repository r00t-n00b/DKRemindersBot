import asyncio
from types import SimpleNamespace

from dkreminders_bot.ui.messages import (
    MSG_VOICE_FAILED_GENERIC,
    MSG_VOICE_TELEGRAM_FILE_FAILED,
    MSG_VOICE_TRANSCRIPTION_FAILED,
)
from dkreminders_bot.integrations.voice_errors import VoiceTelegramFileError, VoiceTranscriptionServiceError
from dkreminders_bot.integrations.voice_remind_flow import handle_voice_remind_command


class FakeChat:
    PRIVATE = "private"


class FakeLogger:
    def __init__(self):
        self.exception_calls = []

    def exception(self, *args, **kwargs):
        self.exception_calls.append((args, kwargs))


class FakeMessage:
    def __init__(self):
        self.replies = []
        self.voice = SimpleNamespace(file_id="voice-file-id")


async def fake_safe_reply(message, text):
    message.replies.append(text)


def build_update():
    message = FakeMessage()
    return SimpleNamespace(
        effective_chat=SimpleNamespace(type=FakeChat.PRIVATE, id=100),
        effective_message=message,
        effective_user=SimpleNamespace(id=200),
        message=message,
    )


def build_deps(transcribe_error):
    async def transcribe_voice_message(update, context):
        raise transcribe_error

    async def remind_command(update, context):
        raise AssertionError("remind_command must not be called on voice errors")

    return SimpleNamespace(
        Chat=FakeChat,
        NormalizedReminderMessageProxy=object,
        SimpleNamespace=SimpleNamespace,
        _normalize_reminder_text_fallback=lambda text: text,
        logger=FakeLogger(),
        remind_command=remind_command,
        safe_reply=fake_safe_reply,
        transcribe_voice_message=transcribe_voice_message,
        type=type,
    )


def test_voice_telegram_file_error_gets_telegram_message():
    update = build_update()
    deps = build_deps(VoiceTelegramFileError("telegram get_file failed"))

    asyncio.run(handle_voice_remind_command(update, SimpleNamespace(), deps))

    assert update.effective_message.replies == [MSG_VOICE_TELEGRAM_FILE_FAILED]


def test_voice_transcription_service_error_gets_transcription_message():
    update = build_update()
    deps = build_deps(VoiceTranscriptionServiceError("gemini overloaded"))

    asyncio.run(handle_voice_remind_command(update, SimpleNamespace(), deps))

    assert update.effective_message.replies == [MSG_VOICE_TRANSCRIPTION_FAILED]


def test_voice_unknown_error_gets_generic_message():
    update = build_update()
    deps = build_deps(RuntimeError("unexpected"))

    asyncio.run(handle_voice_remind_command(update, SimpleNamespace(), deps))

    assert update.effective_message.replies == [MSG_VOICE_FAILED_GENERIC]
