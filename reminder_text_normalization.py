"""Fallback reminder text normalization."""

from typing import Any, Dict, List, Optional, Tuple


_DEP_NAMES = [
    "normalize_gemini_reminder_command_text",
    "normalize_voice_reminder_text",
]


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def normalize_reminder_text_fallback_impl(text: str, deps) -> str:
    _apply_deps(deps)
    normalized = (text or "").strip()
    if not normalized:
        return ""

    if " - " not in normalized:
        fallback_normalized = normalize_voice_reminder_text(normalized)
        if fallback_normalized:
            normalized = fallback_normalized

    normalized = normalize_gemini_reminder_command_text(normalized)

    return normalized
