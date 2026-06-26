"""Dependency factory for _build_reminders_worker_deps."""

import builtins
from types import SimpleNamespace


REMINDERS_WORKER_DEP_SPECS = (
    ("get_chat_type", "_safe_get_chat_type"),
    ("Chat", "Chat"),
    ("add_reminder", "add_reminder"),
    ("asyncio", "asyncio"),
    ("build_group_reminder_keyboard", "build_group_reminder_keyboard"),
    ("build_snooze_keyboard", "build_snooze_keyboard"),
    ("compute_next_occurrence", "compute_next_occurrence"),
    ("get_due_nudges", "get_due_nudges"),
    ("claim_due_reminders", "claim_due_reminders"),
    ("get_due_reminders", "get_due_reminders"),
    ("get_now", "get_now"),
    ("get_recurring_template", "get_recurring_template"),
    ("increment_nudge_count", "increment_nudge_count"),
    ("logger", "logger"),
    ("mark_reminder_delivery_failed", "mark_reminder_delivery_failed"),
    ("mark_reminder_sent", "mark_reminder_sent"),
    ("reset_stale_processing_reminders", "reset_stale_processing_reminders"),
    ("register_reminder_message", "register_reminder_message"),
)


def _resolve_dep(namespace, source_name: str):
    if source_name in namespace:
        return namespace[source_name]
    if hasattr(builtins, source_name):
        return getattr(builtins, source_name)
    raise KeyError(source_name)


def build_reminders_worker_deps(namespace) -> SimpleNamespace:
    values = {}
    missing = []

    for attr_name, source_name in REMINDERS_WORKER_DEP_SPECS:
        try:
            values[attr_name] = _resolve_dep(namespace, source_name)
        except KeyError:
            missing.append(source_name)

    if missing:
        raise KeyError(f"Missing deps for build_reminders_worker_deps: {', '.join(missing)}")

    return SimpleNamespace(**values)
