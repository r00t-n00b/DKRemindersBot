import asyncio
from types import SimpleNamespace

import pytest


class FakePart:
    @staticmethod
    def from_bytes(*, data, mime_type):
        return {
            "data": data,
            "mime_type": mime_type,
        }


class FakeGenaiTypes:
    Part = FakePart


class FakeModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, *, model, contents):
        self.calls.append((model, contents))

        if not self.outcomes:
            raise AssertionError("No fake Gemini outcome left")

        outcome = self.outcomes.pop(0)

        if isinstance(outcome, Exception):
            raise outcome

        return SimpleNamespace(text=outcome)


class FakeClient:
    def __init__(self, outcomes):
        self.models = FakeModels(outcomes)


@pytest.fixture(autouse=True)
def no_retry_sleep_and_fake_genai_types(main_module, monkeypatch):
    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main_module, "genai_types", FakeGenaiTypes)


def test_gemini_transcribe_returns_first_non_empty_text(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "model-a")
    monkeypatch.setenv("GEMINI_TRANSCRIBE_ATTEMPTS", "1")

    client = FakeClient(["завтра 18:00 - купить молоко"])

    result = asyncio.run(
        main_module._gemini_transcribe_audio_with_retries(
            client=client,
            audio_bytes=b"audio",
            aliases_prompt="aliases here",
        )
    )

    assert result == "завтра 18:00 - купить молоко"
    assert [model for model, _contents in client.models.calls] == ["model-a"]

    contents = client.models.calls[0][1]
    prompt = contents[1]
    assert "aliases here" in prompt
    assert "return only one line" in prompt.lower()


def test_gemini_transcribe_retries_empty_text_then_success(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "model-a")
    monkeypatch.setenv("GEMINI_TRANSCRIBE_ATTEMPTS", "2")

    client = FakeClient(["", "через час - проверить духовку"])

    result = asyncio.run(
        main_module._gemini_transcribe_audio_with_retries(
            client=client,
            audio_bytes=b"audio",
        )
    )

    assert result == "через час - проверить духовку"
    assert [model for model, _contents in client.models.calls] == ["model-a", "model-a"]


def test_gemini_transcribe_skips_unsupported_model_and_uses_next(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "bad-model,good-model")
    monkeypatch.setenv("GEMINI_TRANSCRIBE_ATTEMPTS", "3")

    client = FakeClient([
        RuntimeError("404 models/bad-model is not found for API version v1beta, or is not supported for generateContent"),
        "завтра 12:00 - good",
    ])

    result = asyncio.run(
        main_module._gemini_transcribe_audio_with_retries(
            client=client,
            audio_bytes=b"audio",
        )
    )

    assert result == "завтра 12:00 - good"

    # unsupported model should not burn all 3 attempts
    assert [model for model, _contents in client.models.calls] == ["bad-model", "good-model"]


def test_gemini_transcribe_retries_transient_error(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "model-a")
    monkeypatch.setenv("GEMINI_TRANSCRIBE_ATTEMPTS", "2")

    client = FakeClient([
        RuntimeError("503 UNAVAILABLE: The model is overloaded. Please try again later."),
        "завтра 13:00 - retry ok",
    ])

    result = asyncio.run(
        main_module._gemini_transcribe_audio_with_retries(
            client=client,
            audio_bytes=b"audio",
        )
    )

    assert result == "завтра 13:00 - retry ok"
    assert [model for model, _contents in client.models.calls] == ["model-a", "model-a"]


def test_gemini_transcribe_quota_error_raises_billing_message(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "model-a")
    monkeypatch.setenv("GEMINI_TRANSCRIBE_ATTEMPTS", "3")

    client = FakeClient([
        RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded, check your plan and billing details"),
    ])

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(
            main_module._gemini_transcribe_audio_with_retries(
                client=client,
                audio_bytes=b"audio",
            )
        )

    assert "quota/billing limit exceeded" in str(exc.value)
    assert [model for model, _contents in client.models.calls] == ["model-a"]


def test_gemini_transcribe_non_transient_error_raises_immediately(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "model-a")
    monkeypatch.setenv("GEMINI_TRANSCRIBE_ATTEMPTS", "3")

    client = FakeClient([
        ValueError("bad request"),
    ])

    with pytest.raises(ValueError):
        asyncio.run(
            main_module._gemini_transcribe_audio_with_retries(
                client=client,
                audio_bytes=b"audio",
            )
        )

    assert [model for model, _contents in client.models.calls] == ["model-a"]


def test_gemini_transcribe_attempts_env_is_clamped_to_five(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_TRANSCRIBE_MODELS", "model-a")
    monkeypatch.setenv("GEMINI_TRANSCRIBE_ATTEMPTS", "999")

    client = FakeClient(["", "", "", "", "завтра 15:00 - fifth"])

    result = asyncio.run(
        main_module._gemini_transcribe_audio_with_retries(
            client=client,
            audio_bytes=b"audio",
        )
    )

    assert result == "завтра 15:00 - fifth"
    assert len(client.models.calls) == 5
