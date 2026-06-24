"""Dependency factory for _build_voice_remind_command_deps."""

import builtins
from types import SimpleNamespace


VOICE_REMIND_COMMAND_DEP_SPECS = (
    ("Chat", "Chat"),
    ("NormalizedReminderMessageProxy", "NormalizedReminderMessageProxy"),
    ("SimpleNamespace", "SimpleNamespace"),
    ("_normalize_reminder_text_fallback", "_normalize_reminder_text_fallback"),
    ("logger", "logger"),
    ("remind_command", "remind_command"),
    ("safe_reply", "safe_reply"),
    ("transcribe_voice_message", "transcribe_voice_message"),
    ("type", "type"),
)


def _resolve_dep(namespace, source_name: str):
    if source_name in namespace:
        return namespace[source_name]
    if hasattr(builtins, source_name):
        return getattr(builtins, source_name)
    raise KeyError(source_name)


def build_voice_remind_command_deps(namespace) -> SimpleNamespace:
    values = {}
    missing = []

    for attr_name, source_name in VOICE_REMIND_COMMAND_DEP_SPECS:
        try:
            values[attr_name] = _resolve_dep(namespace, source_name)
        except KeyError:
            missing.append(source_name)

    if missing:
        raise KeyError(f"Missing deps for build_voice_remind_command_deps: {', '.join(missing)}")

    return SimpleNamespace(**values)
