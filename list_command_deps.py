"""Dependency factory for _build_list_command_deps."""

import builtins
from types import SimpleNamespace


LIST_COMMAND_DEP_SPECS = (
    ("Chat", "Chat"),
    ("DB_PATH", "DB_PATH"),
    ("sqlite3", "sqlite3"),
    ("build_active_reminders_list_response", "build_active_reminders_list_response"),
    ("build_list_delete_keyboard", "build_list_delete_keyboard"),
    ("build_target_user_presentation_rows", "build_target_user_presentation_rows"),
    ("build_target_user_reminders_list_response", "build_target_user_reminders_list_response"),
    ("format_empty_active_reminders_list_text", "format_empty_active_reminders_list_text"),
    ("get_active_reminders_created_by_for_chat", "get_active_reminders_created_by_for_chat"),
    ("get_all_aliases", "get_all_aliases"),
    ("get_chat_id_by_alias_for_user", "get_chat_id_by_alias_for_user"),
    ("get_now", "get_now"),
    ("get_private_chat_id_by_username", "get_private_chat_id_by_username"),
    ("get_recurring_template", "get_recurring_template"),
    ("get_user_alias_chat_id_for_user", "get_user_alias_chat_id_for_user"),
    ("safe_reply", "safe_reply"),
)


def _resolve_dep(namespace, source_name: str):
    if source_name in namespace:
        return namespace[source_name]
    if hasattr(builtins, source_name):
        return getattr(builtins, source_name)
    raise KeyError(source_name)


def build_list_command_deps(namespace) -> SimpleNamespace:
    values = {}
    missing = []

    for attr_name, source_name in LIST_COMMAND_DEP_SPECS:
        try:
            values[attr_name] = _resolve_dep(namespace, source_name)
        except KeyError:
            missing.append(source_name)

    if missing:
        raise KeyError(f"Missing deps for build_list_command_deps: {', '.join(missing)}")

    return SimpleNamespace(**values)
