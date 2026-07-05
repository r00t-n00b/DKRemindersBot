import asyncio
from types import SimpleNamespace

import main
from dkreminders_bot.integrations.plain_text_gemini_normalization import normalize_plain_text_reminder_with_gemini_impl


class Logger:
    def __init__(self):
        self.infos = []
        self.warnings = []

    def info(self, *args):
        self.infos.append(args)

    def warning(self, *args):
        self.warnings.append(args)


class FakeModels:
    def __init__(self, result_text=None, errors=None):
        self.result_text = result_text
        self.errors = list(errors or [])
        self.calls = []

    def generate_content(self, *, model, contents):
        self.calls.append((model, contents))
        if self.errors:
            raise self.errors.pop(0)
        return SimpleNamespace(text=self.result_text)


class FakeGenAI:
    def __init__(self, models):
        self._models = models
        self.clients = []

    def Client(self, *, api_key):
        client = SimpleNamespace(api_key=api_key, models=self._models)
        self.clients.append(client)
        return client


def test_plain_text_gemini_normalization_returns_empty_for_blank_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "token")
    logger = Logger()
    models = FakeModels(result_text="tomorrow 10:00 - milk")

    result = asyncio.run(normalize_plain_text_reminder_with_gemini_impl(
        "   ",
        42,
        genai=FakeGenAI(models),
        logger=logger,
        format_known_aliases_for_voice_prompt=lambda created_by: "Aliases: none",
        is_unsupported_gemini_model_error=lambda exc: False,
        is_gemini_quota_error=lambda exc: False,
        is_transient_gemini_error=lambda exc: False,
    ))

    assert result == ""
    assert models.calls == []


def test_plain_text_gemini_normalization_requires_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    try:
        asyncio.run(normalize_plain_text_reminder_with_gemini_impl(
            "напомни завтра молоко",
            42,
            genai=FakeGenAI(FakeModels(result_text="tomorrow - milk")),
            logger=Logger(),
            format_known_aliases_for_voice_prompt=lambda created_by: "Aliases: none",
            is_unsupported_gemini_model_error=lambda exc: False,
            is_gemini_quota_error=lambda exc: False,
            is_transient_gemini_error=lambda exc: False,
        ))
    except RuntimeError as exc:
        assert "GEMINI_API_KEY не задан" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_plain_text_gemini_normalization_uses_models_and_alias_prompt(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "token")
    monkeypatch.setenv("GEMINI_TEXT_NORMALIZE_MODELS", "model-a, model-b")
    monkeypatch.setenv("GEMINI_MODEL_CALL_TIMEOUT_SECONDS", "1")

    logger = Logger()
    models = FakeModels(result_text="завтра 10:00 - молоко")

    result = asyncio.run(normalize_plain_text_reminder_with_gemini_impl(
        "напомни завтра в 10 купить молоко",
        42,
        genai=FakeGenAI(models),
        logger=logger,
        format_known_aliases_for_voice_prompt=lambda created_by: "Known aliases: home",
        is_unsupported_gemini_model_error=lambda exc: False,
        is_gemini_quota_error=lambda exc: False,
        is_transient_gemini_error=lambda exc: False,
    ))

    assert result == "завтра 10:00 - молоко"
    assert models.calls[0][0] == "model-a"
    assert "Known aliases: home" in models.calls[0][1][0]
    assert "напомни завтра в 10 купить молоко" in models.calls[0][1][0]
    assert logger.infos


def test_plain_text_gemini_normalization_skips_unsupported_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "token")
    monkeypatch.setenv("GEMINI_TEXT_NORMALIZE_MODELS", "bad-model, good-model")
    monkeypatch.setenv("GEMINI_MODEL_CALL_TIMEOUT_SECONDS", "1")

    logger = Logger()
    unsupported = RuntimeError("unsupported")
    models = FakeModels(result_text="tomorrow 10:00 - milk", errors=[unsupported])

    result = asyncio.run(normalize_plain_text_reminder_with_gemini_impl(
        "remind me tomorrow 10 milk",
        42,
        genai=FakeGenAI(models),
        logger=logger,
        format_known_aliases_for_voice_prompt=lambda created_by: "Aliases: none",
        is_unsupported_gemini_model_error=lambda exc: exc is unsupported,
        is_gemini_quota_error=lambda exc: False,
        is_transient_gemini_error=lambda exc: False,
    ))

    assert result == "tomorrow 10:00 - milk"
    assert [call[0] for call in models.calls] == ["bad-model", "good-model"]
    assert logger.warnings


def test_plain_text_gemini_normalization_raises_quota_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "token")
    monkeypatch.setenv("GEMINI_TEXT_NORMALIZE_MODELS", "model-a")
    monkeypatch.setenv("GEMINI_MODEL_CALL_TIMEOUT_SECONDS", "1")

    quota = RuntimeError("quota")
    models = FakeModels(errors=[quota])

    try:
        asyncio.run(normalize_plain_text_reminder_with_gemini_impl(
            "remind me tomorrow 10 milk",
            42,
            genai=FakeGenAI(models),
            logger=Logger(),
            format_known_aliases_for_voice_prompt=lambda created_by: "Aliases: none",
            is_unsupported_gemini_model_error=lambda exc: False,
            is_gemini_quota_error=lambda exc: exc is quota,
            is_transient_gemini_error=lambda exc: False,
        ))
    except RuntimeError as exc:
        assert "Gemini quota/billing limit exceeded" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_main_plain_text_gemini_normalization_is_thin_wrapper():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    node = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "normalize_plain_text_reminder_with_gemini"
    ][0]

    wrapper_source = ast.get_source_segment(source, node)

    assert "normalize_plain_text_reminder_with_gemini_impl(" in wrapper_source
    assert "You are normalizing a Telegram text message" not in wrapper_source
    assert node.end_lineno - node.lineno + 1 <= 12


def test_main_reexports_plain_text_gemini_normalizer_impl():
    assert main.normalize_plain_text_reminder_with_gemini_impl is normalize_plain_text_reminder_with_gemini_impl
