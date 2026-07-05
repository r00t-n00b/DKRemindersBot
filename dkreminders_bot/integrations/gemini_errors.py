"""Gemini error classification helpers."""


def _is_transient_gemini_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return (
        "500" in text
        or "internal" in text
        or "503" in text
        or "unavailable" in text
        or "high demand" in text
        or "temporar" in text
        or "deadline_exceeded" in text
        or "429" in text
        or "resource_exhausted" in text
    )


def _is_unsupported_gemini_model_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return (
        "404" in text
        and (
            "not_found" in text
            or "is not found" in text
            or "not supported for generatecontent" in text
            or "listmodels" in text
        )
    )


def _is_gemini_quota_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return (
        "429" in text
        and (
            "resource_exhausted" in text
            or "quota exceeded" in text
            or "check your plan and billing" in text
            or "free_tier" in text
            or "limit: 0" in text
        )
    )
