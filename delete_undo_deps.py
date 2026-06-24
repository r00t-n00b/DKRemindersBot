"""Dependency list for delete/undo callback router."""

from types import SimpleNamespace


DELETE_UNDO_CALLBACK_DEP_NAMES = (
    "CTX",
    "DB_PATH",
    "InlineKeyboardButton",
    "InlineKeyboardMarkup",
    "MSG_DELETE_FAILED_SHORT",
    "MSG_DELETE_SERIES_FAILED",
    "MSG_REMINDER_ALREADY_DELETED_ALERT",
    "MSG_UNDO_EXPIRED",
    "MSG_UNDO_RESTORE_FAILED",
    "Update",
    "build_active_reminders_list_response",
    "build_created_reminder_actions_keyboard",
    "build_created_reminder_actions_keyboard_for_reminder",
    "build_list_delete_keyboard",
    "build_recurring_delete_choice_keyboard",
    "cb_undo",
    "datetime",
    "delete_recurring_one_instance_and_reschedule",
    "delete_recurring_series_with_snapshot",
    "delete_single_reminder_with_snapshot",
    "format_deleted_human",
    "format_deleted_snapshot_text",
    "format_recurring_human",
    "format_restored_series_text",
    "format_restored_single_text",
    "get_now",
    "get_recurring_template_row",
    "get_reminder_row",
    "logger",
    "make_undo_token",
    "restore_deleted_snapshot",
    "sqlite3",
)


def build_delete_undo_callback_deps(namespace) -> SimpleNamespace:
    missing = [name for name in DELETE_UNDO_CALLBACK_DEP_NAMES if name not in namespace]
    if missing:
        raise KeyError(f"Missing delete/undo callback deps: {', '.join(missing)}")

    return SimpleNamespace(
        **{name: namespace[name] for name in DELETE_UNDO_CALLBACK_DEP_NAMES}
    )
