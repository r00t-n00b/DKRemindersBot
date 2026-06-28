import asyncio
from types import SimpleNamespace

import gemini_transcription


class FakeLogger:
    def __init__(self):
        self.info_calls = []
        self.warning_calls = []

    def info(self, *args, **kwargs):
        self.info_calls.append((args, kwargs))

    def warning(self, *args, **kwargs):
        self.warning_calls.append((args, kwargs))


class FakePart:
    @staticmethod
    def from_bytes(*, data, mime_type):
        return SimpleNamespace(data=data, mime_type=mime_type)


class FakeGenaiTypes:
    Part = FakePart


class FakeModels:
    def generate_content(self, **kwargs):
        raise AssertionError("generate_content is executed through asyncio.to_thread and is mocked by wait_for")


class FakeClient:
    models = FakeModels()


async def _no_sleep(delay):
    return None


def test_gemini_transcription_timeout_falls_back_to_next_model(monkeypatch):
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "slow-model,fast-model")
    monkeypatch.setenv("GEMINI_TRANSCRIBE_ATTEMPTS", "1")
    monkeypatch.setenv("GEMINI_TRANSCRIBE_ATTEMPT_TIMEOUT_SEC", "3")
    monkeypatch.setattr(gemini_transcription.asyncio, "sleep", _no_sleep)

    calls = []

    async def fake_wait_for(awaitable, timeout):
        calls.append(timeout)
        if hasattr(awaitable, "close"):
            awaitable.close()

        if len(calls) == 1:
            raise asyncio.TimeoutError()

        return SimpleNamespace(text="завтра 10:00 - тест")

    monkeypatch.setattr(gemini_transcription.asyncio, "wait_for", fake_wait_for)

    result = asyncio.run(
        gemini_transcription.gemini_transcribe_audio_with_retries(
            client=FakeClient(),
            audio_bytes=b"audio",
            genai_types=FakeGenaiTypes,
            logger=FakeLogger(),
        )
    )

    assert result == "завтра 10:00 - тест"
    assert calls == [3.0, 3.0]
