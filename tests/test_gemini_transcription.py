import asyncio
from types import SimpleNamespace

import pytest

import main
from dkreminders_bot.integrations.gemini_transcription import gemini_transcribe_audio_with_retries


class FakePart:
    @staticmethod
    def from_bytes(data, mime_type):
        return {"data": data, "mime_type": mime_type}


class FakeGenaiTypes:
    Part = FakePart


class FakeLogger:
    def __init__(self):
        self.info_calls = []
        self.warning_calls = []

    def info(self, *args):
        self.info_calls.append(args)

    def warning(self, *args):
        self.warning_calls.append(args)


class FakeModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_content(self, *, model, contents):
        self.calls.append({"model": model, "contents": contents})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(text=response)


class FakeClient:
    def __init__(self, responses):
        self.models = FakeModels(responses)


def test_gemini_transcribe_audio_with_retries_returns_clean_text(monkeypatch):
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "model-a")
    logger = FakeLogger()
    client = FakeClient(["  normalized reminder  "])

    async def run():
        return await gemini_transcribe_audio_with_retries(
            client=client,
            audio_bytes=b"voice",
            genai_types=FakeGenaiTypes,
            logger=logger,
            aliases_prompt="Known aliases block",
        )

    result = asyncio.run(run())

    assert result == "normalized reminder"
    assert client.models.calls[0]["model"] == "model-a"
    assert client.models.calls[0]["contents"][0] == {"data": b"voice", "mime_type": "audio/ogg"}
    assert "Known aliases block" in client.models.calls[0]["contents"][1]
    assert logger.info_calls


def test_gemini_transcribe_audio_with_retries_falls_back_after_unsupported_model(monkeypatch):
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "bad-model,good-model")
    logger = FakeLogger()
    client = FakeClient([
        RuntimeError("404 NOT_FOUND model is not found, use ListModels"),
        "ok",
    ])

    async def run():
        return await gemini_transcribe_audio_with_retries(
            client=client,
            audio_bytes=b"voice",
            genai_types=FakeGenaiTypes,
            logger=logger,
        )

    result = asyncio.run(run())

    assert result == "ok"
    assert [call["model"] for call in client.models.calls] == ["bad-model", "good-model"]
    assert logger.warning_calls


def test_gemini_transcribe_audio_with_retries_raises_billing_message_on_quota(monkeypatch):
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "model-a")
    logger = FakeLogger()
    client = FakeClient([RuntimeError("429 quota exceeded check your plan and billing")])

    async def run():
        return await gemini_transcribe_audio_with_retries(
            client=client,
            audio_bytes=b"voice",
            genai_types=FakeGenaiTypes,
            logger=logger,
        )

    with pytest.raises(RuntimeError, match="Gemini quota/billing limit exceeded"):
        asyncio.run(run())


def test_main_wrapper_keeps_old_transcription_helper_contract(monkeypatch):
    async def fake_helper(**kwargs):
        assert kwargs["genai_types"] is main.genai_types
        assert kwargs["logger"] is main.logger
        assert kwargs["audio_bytes"] == b"voice"
        return "ok"

    monkeypatch.setattr(main, "gemini_transcribe_audio_with_retries", fake_helper)

    async def run():
        return await main._gemini_transcribe_audio_with_retries(
            client=object(),
            audio_bytes=b"voice",
            aliases_prompt="aliases",
        )

    assert asyncio.run(run()) == "ok"


def test_gemini_transcription_body_is_no_longer_in_main_source():
    from pathlib import Path

    source = Path("main.py").read_text()

    assert "GEMINI_TRANSCRIPTION_SUCCESS" not in source
    assert "genai_types.Part.from_bytes" not in source
    assert "Gemini временно не смог распознать голосовое" not in source
    assert "from dkreminders_bot.integrations.gemini_transcription import gemini_transcribe_audio_with_retries" in source
