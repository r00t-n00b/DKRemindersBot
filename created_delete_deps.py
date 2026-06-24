"""Dependency factory for _build_created_delete_callback_deps."""

import builtins
from types import SimpleNamespace


CREATED_DELETE_CALLBACK_DEP_SPECS = (
    ("InlineKeyboardButton", "InlineKeyboardButton"),
    ("InlineKeyboardMarkup", "InlineKeyboardMarkup"),
    ("MSG_DELETE_FAILED_SHORT", "MSG_DELETE_FAILED_SHORT"),
    ("MSG_DELETE_FAILED_TEXT", "MSG_DELETE_FAILED_TEXT"),
    ("MSG_REMINDER_ALREADY_DELETED_ALERT", "MSG_REMINDER_ALREADY_DELETED_ALERT"),
    ("MSG_REMINDER_ALREADY_DELETED_TEXT", "MSG_REMINDER_ALREADY_DELETED_TEXT"),
    ("build_recurring_delete_choice_keyboard", "build_recurring_delete_choice_keyboard"),
    ("cb_undo", "cb_undo"),
    ("delete_single_reminder_with_snapshot", "delete_single_reminder_with_snapshot"),
    ("dict", "dict"),
    ("format_deleted_human", "format_deleted_human"),
    ("get_reminder_row", "get_reminder_row"),
    ("make_undo_token", "make_undo_token"),
)


def _resolve_dep(namespace, source_name: str):
    if source_name in namespace:
        return namespace[source_name]
    if hasattr(builtins, source_name):
        return getattr(builtins, source_name)
    raise KeyError(source_name)


def build_created_delete_callback_deps(namespace) -> SimpleNamespace:
    values = {}
    missing = []

    for attr_name, source_name in CREATED_DELETE_CALLBACK_DEP_SPECS:
        try:
            values[attr_name] = _resolve_dep(namespace, source_name)
        except KeyError:
            missing.append(source_name)

    if missing:
        raise KeyError(f"Missing deps for build_created_delete_callback_deps: {', '.join(missing)}")

    return SimpleNamespace(**values)
