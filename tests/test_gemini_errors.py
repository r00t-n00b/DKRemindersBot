import main
from dkreminders_bot.integrations.gemini_errors import (
    _is_gemini_quota_error,
    _is_transient_gemini_error,
    _is_unsupported_gemini_model_error,
)


def test_transient_gemini_error_detection():
    assert _is_transient_gemini_error(RuntimeError("500 internal error"))
    assert _is_transient_gemini_error(RuntimeError("503 unavailable"))
    assert _is_transient_gemini_error(RuntimeError("deadline_exceeded"))
    assert _is_transient_gemini_error(RuntimeError("429 resource_exhausted"))
    assert not _is_transient_gemini_error(RuntimeError("400 bad request"))


def test_unsupported_gemini_model_error_detection():
    assert _is_unsupported_gemini_model_error(
        RuntimeError("404 NOT_FOUND model is not found, use ListModels")
    )
    assert _is_unsupported_gemini_model_error(
        RuntimeError("404 not supported for generateContent")
    )
    assert not _is_unsupported_gemini_model_error(RuntimeError("500 internal"))


def test_gemini_quota_error_detection():
    assert _is_gemini_quota_error(RuntimeError("429 resource_exhausted"))
    assert _is_gemini_quota_error(RuntimeError("429 quota exceeded"))
    assert _is_gemini_quota_error(RuntimeError("429 check your plan and billing"))
    assert _is_gemini_quota_error(RuntimeError("429 free_tier limit: 0"))
    assert not _is_gemini_quota_error(RuntimeError("503 unavailable"))


def test_main_reexports_gemini_error_helpers_for_existing_callers():
    assert main._is_transient_gemini_error is _is_transient_gemini_error
    assert main._is_unsupported_gemini_model_error is _is_unsupported_gemini_model_error
    assert main._is_gemini_quota_error is _is_gemini_quota_error


def test_gemini_error_classifiers_are_no_longer_defined_in_main_source():
    from pathlib import Path

    source = Path("main.py").read_text()

    assert "def _is_transient_gemini_error(" not in source
    assert "def _is_unsupported_gemini_model_error(" not in source
    assert "def _is_gemini_quota_error(" not in source
    assert "from dkreminders_bot.integrations.gemini_errors import (" in source
