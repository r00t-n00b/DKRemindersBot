"""Dependency list for created-snooze callback router."""

from types import SimpleNamespace


CREATED_SNOOZE_CALLBACK_DEP_NAMES = (
    "MSG_INVALID_REMINDER_ID",
    "MSG_RESCHEDULE_BAD_DATETIME",
    "MSG_RESCHEDULE_PAST_TIME",
    "MSG_RESCHEDULE_UNKNOWN_ACTION",
    "MSG_UNEXPECTED_CALLBACK_ERROR",
    "TZ",
    "_answer_created_action_reminder_missing",
    "_ensure_created_action_reminder_exists",
    "build_created_reminder_actions_keyboard_for_reminder",
    "build_created_reschedule_keyboard",
    "build_custom_date_keyboard",
    "build_custom_time_keyboard",
    "compute_snooze_target_time",
    "datetime",
    "get_now",
    "get_reminder",
    "get_user_default_time",
    "logger",
    "update_reminder_time",
)


def build_created_snooze_callback_deps(namespace) -> SimpleNamespace:
    missing = [name for name in CREATED_SNOOZE_CALLBACK_DEP_NAMES if name not in namespace]
    if missing:
        raise KeyError(f"Missing created-snooze callback deps: {', '.join(missing)}")

    return SimpleNamespace(
        **{name: namespace[name] for name in CREATED_SNOOZE_CALLBACK_DEP_NAMES}
    )
