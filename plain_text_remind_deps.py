"""Dependency factory for _build_plain_text_remind_command_deps."""

import builtins
from types import SimpleNamespace


PLAIN_TEXT_REMIND_COMMAND_DEP_SPECS = (
    ("Chat", "Chat"),
    ("MSG_NOT_UNDERSTOOD_PLAIN_TEXT", "MSG_NOT_UNDERSTOOD_PLAIN_TEXT"),
    ("NormalizedReminderMessageProxy", "NormalizedReminderMessageProxy"),
    ("SimpleNamespace", "SimpleNamespace"),
    ("_normalize_plain_text_relative_reminder_locally", "_normalize_plain_text_relative_reminder_locally"),
    ("_normalize_plain_text_reminder_locally", "_normalize_plain_text_reminder_locally"),
    ("_normalize_reminder_text_fallback", "_normalize_reminder_text_fallback"),
    ("logger", "logger"),
    ("normalize_gemini_reminder_command_text", "normalize_gemini_reminder_command_text"),
    ("normalize_plain_text_reminder_with_gemini", "normalize_plain_text_reminder_with_gemini"),
    ("remind_command", "remind_command"),
    ("safe_reply", "safe_reply"),
    ("type", "type"),
)


def _resolve_dep(namespace, source_name: str):
    if source_name in namespace:
        return namespace[source_name]
    if hasattr(builtins, source_name):
        return getattr(builtins, source_name)
    raise KeyError(source_name)


def build_plain_text_remind_command_deps(namespace) -> SimpleNamespace:
    values = {}
    missing = []

    for attr_name, source_name in PLAIN_TEXT_REMIND_COMMAND_DEP_SPECS:
        try:
            values[attr_name] = _resolve_dep(namespace, source_name)
        except KeyError:
            missing.append(source_name)

    if missing:
        raise KeyError(f"Missing deps for build_plain_text_remind_command_deps: {', '.join(missing)}")

    return SimpleNamespace(**values)
