"""Dependency factory for _build_reminder_text_normalization_deps."""

import builtins
from types import SimpleNamespace


REMINDER_TEXT_NORMALIZATION_DEP_SPECS = (
    ("normalize_gemini_reminder_command_text", "normalize_gemini_reminder_command_text"),
    ("normalize_voice_reminder_text", "normalize_voice_reminder_text"),
)


def _resolve_dep(namespace, source_name: str):
    if source_name in namespace:
        return namespace[source_name]
    if hasattr(builtins, source_name):
        return getattr(builtins, source_name)
    raise KeyError(source_name)


def build_reminder_text_normalization_deps(namespace) -> SimpleNamespace:
    values = {}
    missing = []

    for attr_name, source_name in REMINDER_TEXT_NORMALIZATION_DEP_SPECS:
        try:
            values[attr_name] = _resolve_dep(namespace, source_name)
        except KeyError:
            missing.append(source_name)

    if missing:
        raise KeyError(f"Missing deps for build_reminder_text_normalization_deps: {', '.join(missing)}")

    return SimpleNamespace(**values)
