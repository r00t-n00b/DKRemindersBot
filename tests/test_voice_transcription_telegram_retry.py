import asyncio
import os
from types import SimpleNamespace

import pytest

import dkreminders_bot.integrations.voice_transcription as voice_transcription
from dkreminders_bot.integrations.voice_errors import VoiceTelegramFileError
from dkreminders_bot.integrations.voice_transcription import transcribe_voice_message_impl


class FakeLogger:
    def __init__(self):
        self.info_calls = []
        self.warning_calls = []

    def info(self, *args, **kwargs):
        self.info_calls.append((args, kwargs))

    def warning(self, *args, **kwargs):
        self.warning_calls.append((args, kwargs))


class FakeGenai:
    class Client:
        def __init__(self, api_key):
            self.api_key = api_key


class FakeBot:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def get_file(self, file_id):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def build_update():
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=123),
        effective_message=SimpleNamespace(
            voice=SimpleNamespace(file_id="voice-file-id"),
        ),
    )


def build_deps(*, download, gemini=None, logger=None):
    async def default_gemini(**kwargs):
        return "завтра 10:00 тест"

    return SimpleNamespace(
        _format_known_aliases_for_voice_prompt=lambda user_id: "",
        _gemini_transcribe_audio_with_retries=gemini or default_gemini,
        download_telegram_file_bytes=download,
        genai=FakeGenai,
        genai_types=object(),
        logger=logger or FakeLogger(),
        os=os,
    )


async def _no_sleep(delay):
    return None


def test_transcribe_voice_retries_telegram_get_file_timeout(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-token")
    monkeypatch.setattr(voice_transcription.asyncio, "sleep", _no_sleep)

    bot = FakeBot([
        TimeoutError("first timeout"),
        SimpleNamespace(file_path="ok"),
    ])

    async def download(tg_file, suffix):
        return b"audio"

    deps = build_deps(download=download)
    context = SimpleNamespace(bot=bot)

    result = asyncio.run(transcribe_voice_message_impl(build_update(), context, deps))

    assert result == "завтра 10:00 тест"
    assert bot.calls == 2


def test_transcribe_voice_wraps_telegram_get_file_failure(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-token")
    monkeypatch.setattr(voice_transcription.asyncio, "sleep", _no_sleep)

    bot = FakeBot([
        TimeoutError("first timeout"),
        TimeoutError("second timeout"),
        TimeoutError("third timeout"),
    ])

    async def download(tg_file, suffix):
        raise AssertionError("download must not be called when get_file fails")

    deps = build_deps(download=download)
    context = SimpleNamespace(bot=bot)

    with pytest.raises(VoiceTelegramFileError):
        asyncio.run(transcribe_voice_message_impl(build_update(), context, deps))

    assert bot.calls == 3
