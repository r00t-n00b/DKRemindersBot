import asyncio
import time

import pytest


def test_gemini_text_normalize_model_call_timeout_does_not_wait_for_blocking_sdk(main_module, monkeypatch):
    calls = []

    class FakeModels:
        def generate_content(self, **kwargs):
            raise AssertionError("generate_content should be routed through asyncio.to_thread in this test")

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    class FakeGenAI:
        Client = FakeClient

    async def fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        await asyncio.sleep(1)
        return None

    monkeypatch.setattr(main_module, "genai", FakeGenAI)
    monkeypatch.setattr(main_module.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setenv("GEMINI_API_KEY", "test-token")
    monkeypatch.setenv("GEMINI_TEXT_NORMALIZE_MODELS", "slow-model")
    monkeypatch.setenv("GEMINI_MODEL_CALL_TIMEOUT_SECONDS", "0.01")

    started = time.monotonic()

    with pytest.raises(RuntimeError) as exc:
        asyncio.run(
            main_module.normalize_plain_text_reminder_with_gemini(
                "напомни 1 октября пересчитать стоимость начинки квартиры",
                123,
            )
        )

    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert "Gemini временно не смог нормализовать текст" in str(exc.value)
    assert len(calls) == 1
    assert calls[0][2]["model"] == "slow-model"
