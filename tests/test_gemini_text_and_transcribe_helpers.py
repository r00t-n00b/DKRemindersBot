import asyncio
from types import SimpleNamespace

import pytest


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


class FakeGenai:
    def __init__(self, client):
        self._client = client

    def Client(self, *, api_key):
        assert api_key == "fake-key"
        return self._client


class FakeTGFile:
    def __init__(self, data=b"voice-bytes"):
        self.data = data
        self.downloaded_to = None

    async def download_to_drive(self, path):
        self.downloaded_to = path
        with open(path, "wb") as f:
            f.write(self.data)


class FakeBot:
    def __init__(self, tg_file):
        self.tg_file = tg_file

    async def get_file(self, file_id):
        assert file_id == "voice-file-id"
        return self.tg_file


class FakeVoice:
    file_id = "voice-file-id"


def _mk_voice_update(user_id=123):
    message = SimpleNamespace(voice=FakeVoice())
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=user_id),
    )
    return update


def test_normalize_reminder_text_fallback_removes_remind_prefix_and_adds_dash(main_module):
    assert (
        main_module._normalize_reminder_text_fallback("напомни завтра в 18:00 купить молоко")
        == "завтра 18:00 - купить молоко"
    )

    assert (
        main_module._normalize_reminder_text_fallback("remind me at 11 buy milk")
        == "11:00 - buy milk"
    )


def test_normalize_reminder_text_fallback_keeps_already_normalized_text(main_module):
    assert (
        main_module._normalize_reminder_text_fallback("завтра 18:00 - купить молоко")
        == "завтра 18:00 - купить молоко"
    )


def test_format_known_aliases_for_voice_prompt_lists_user_and_chat_aliases_sorted(main_module):
    main_module.set_user_alias("Natasha", 42, 4242, "natasha", created_by=123)
    main_module.set_user_alias("misha", 43, 4343, "misha", created_by=123)

    main_module.set_chat_alias("Football", 777, "Football Chat", created_by=123)
    main_module.set_chat_alias("home", 888, "Home Chat", created_by=123)

    # Other owner's aliases must not leak into prompt.
    main_module.set_user_alias("OtherUser", 99, 9999, "other", created_by=999)
    main_module.set_chat_alias("OtherChat", 999, "Other Chat", created_by=999)

    prompt = main_module._format_known_aliases_for_voice_prompt(123)

    assert "Known user aliases:" in prompt
    assert "- misha" in prompt
    assert "- Natasha" in prompt

    assert "Known chat aliases:" in prompt
    assert "- Football" in prompt
    assert "- home" in prompt

    assert "OtherUser" not in prompt
    assert "OtherChat" not in prompt


def test_format_known_aliases_for_voice_prompt_handles_alias_lookup_errors(main_module, monkeypatch):
    def fail_user_aliases(created_by):
        raise RuntimeError("db unavailable")

    def fail_chat_aliases(created_by):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(main_module, "get_all_user_aliases", fail_user_aliases)
    monkeypatch.setattr(main_module, "get_all_aliases", fail_chat_aliases)

    prompt = main_module._format_known_aliases_for_voice_prompt(123)

    assert "Known user aliases:" in prompt
    assert "Known chat aliases:" in prompt
    assert prompt.count("- none") == 2


def test_normalize_plain_text_reminder_with_gemini_returns_normalized_text(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("GEMINI_TEXT_NORMALIZE_MODELS", "model-a")

    client = FakeClient(["завтра 18:00 - купить молоко"])
    monkeypatch.setattr(main_module, "genai", FakeGenai(client))

    result = asyncio.run(
        main_module.normalize_plain_text_reminder_with_gemini(
            "напомни завтра купить молоко",
            created_by=123,
        )
    )

    assert result == "завтра 18:00 - купить молоко"
    assert [model for model, _contents in client.models.calls] == ["model-a"]

    prompt = client.models.calls[0][1][0]
    assert "Return only one line" in prompt
    assert "NO_REMINDER" in prompt
    assert "User message:" in prompt
    assert "напомни завтра купить молоко" in prompt


def test_normalize_plain_text_reminder_with_gemini_skips_unsupported_model(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("GEMINI_TEXT_NORMALIZE_MODELS", "bad-model,good-model")

    client = FakeClient([
        RuntimeError("404 models/bad-model is not found for API version v1beta, or is not supported for generateContent"),
        "завтра 19:00 - good",
    ])
    monkeypatch.setattr(main_module, "genai", FakeGenai(client))

    result = asyncio.run(
        main_module.normalize_plain_text_reminder_with_gemini(
            "напомни завтра good",
            created_by=123,
        )
    )

    assert result == "завтра 19:00 - good"
    assert [model for model, _contents in client.models.calls] == ["bad-model", "good-model"]


def test_normalize_plain_text_reminder_with_gemini_quota_error_raises_billing_message(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("GEMINI_TEXT_NORMALIZE_MODELS", "model-a")

    client = FakeClient([
        RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded, check your plan and billing details"),
    ])
    monkeypatch.setattr(main_module, "genai", FakeGenai(client))

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(
            main_module.normalize_plain_text_reminder_with_gemini(
                "напомни завтра good",
                created_by=123,
            )
        )

    assert "quota/billing limit exceeded" in str(exc.value)
    assert [model for model, _contents in client.models.calls] == ["model-a"]


def test_normalize_plain_text_reminder_with_gemini_non_transient_error_raises(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("GEMINI_TEXT_NORMALIZE_MODELS", "model-a")

    client = FakeClient([ValueError("bad request")])
    monkeypatch.setattr(main_module, "genai", FakeGenai(client))

    with pytest.raises(ValueError):
        asyncio.run(
            main_module.normalize_plain_text_reminder_with_gemini(
                "напомни завтра good",
                created_by=123,
            )
        )


def test_normalize_plain_text_reminder_with_gemini_requires_api_key(main_module, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        asyncio.run(
            main_module.normalize_plain_text_reminder_with_gemini(
                "напомни завтра good",
                created_by=123,
            )
        )


def test_transcribe_voice_message_downloads_audio_and_calls_gemini_retry(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(main_module, "genai_types", object())

    tg_file = FakeTGFile(data=b"audio-bytes")
    context = SimpleNamespace(bot=FakeBot(tg_file))
    update = _mk_voice_update(user_id=123)

    called = {}

    class FakeClientFactory:
        def Client(self, *, api_key):
            assert api_key == "fake-key"
            return "fake-client"

    async def fake_retry(*, client, audio_bytes, aliases_prompt):
        called["client"] = client
        called["audio_bytes"] = audio_bytes
        called["aliases_prompt"] = aliases_prompt
        return "завтра 18:00 - купить молоко"

    monkeypatch.setattr(main_module, "genai", FakeClientFactory())
    monkeypatch.setattr(main_module, "_gemini_transcribe_audio_with_retries", fake_retry)
    monkeypatch.setattr(main_module, "_format_known_aliases_for_voice_prompt", lambda created_by: f"aliases for {created_by}")

    result = asyncio.run(main_module.transcribe_voice_message(update, context))

    assert result == "завтра 18:00 - купить молоко"
    assert called == {
        "client": "fake-client",
        "audio_bytes": b"audio-bytes",
        "aliases_prompt": "aliases for 123",
    }


def test_transcribe_voice_message_rejects_empty_telegram_audio(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(main_module, "genai_types", object())
    monkeypatch.setattr(main_module, "genai", object())

    tg_file = FakeTGFile(data=b"")
    context = SimpleNamespace(bot=FakeBot(tg_file))
    update = _mk_voice_update(user_id=123)

    with pytest.raises(RuntimeError, match="Telegram voice file пустой"):
        asyncio.run(main_module.transcribe_voice_message(update, context))


def test_transcribe_voice_message_validates_input(main_module, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(main_module, "genai_types", object())
    monkeypatch.setattr(main_module, "genai", object())

    context = SimpleNamespace(bot=FakeBot(FakeTGFile()))

    with pytest.raises(ValueError, match="Нет пользователя"):
        asyncio.run(
            main_module.transcribe_voice_message(
                SimpleNamespace(effective_message=SimpleNamespace(voice=FakeVoice()), effective_user=None),
                context,
            )
        )

    with pytest.raises(ValueError, match="Нет голосового сообщения"):
        asyncio.run(
            main_module.transcribe_voice_message(
                SimpleNamespace(effective_message=SimpleNamespace(voice=None), effective_user=SimpleNamespace(id=123)),
                context,
            )
        )
