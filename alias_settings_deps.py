"""Dependency factory for _build_alias_settings_command_deps."""

import builtins
from types import SimpleNamespace


ALIAS_SETTINGS_COMMAND_DEP_SPECS = (
    ("Chat", "Chat"),
    ("clear_user_default_time", "clear_user_default_time"),
    ("delete_chat_alias", "delete_chat_alias"),
    ("delete_user_alias", "delete_user_alias"),
    ("format_default_time_value", "format_default_time_value"),
    ("get_all_aliases", "get_all_aliases"),
    ("get_all_user_aliases", "get_all_user_aliases"),
    ("get_chat_id_by_alias", "get_chat_id_by_alias"),
    ("get_user_alias", "get_user_alias"),
    ("get_user_chat_id_by_username", "get_user_chat_id_by_username"),
    ("get_user_default_time", "get_user_default_time"),
    ("logger", "logger"),
    ("parse_default_time_value", "parse_default_time_value"),
    ("parse_renamealias_args", "parse_renamealias_args"),
    ("rename_chat_alias", "rename_chat_alias"),
    ("rename_user_alias", "rename_user_alias"),
    ("safe_reply", "safe_reply"),
    ("set_chat_alias_for_user", "set_chat_alias_for_user"),
    ("set_user_alias", "set_user_alias"),
    ("set_user_default_time", "set_user_default_time"),
)


def _resolve_dep(namespace, source_name: str):
    if source_name in namespace:
        return namespace[source_name]
    if hasattr(builtins, source_name):
        return getattr(builtins, source_name)
    raise KeyError(source_name)


def build_alias_settings_command_deps(namespace) -> SimpleNamespace:
    values = {}
    missing = []

    for attr_name, source_name in ALIAS_SETTINGS_COMMAND_DEP_SPECS:
        try:
            values[attr_name] = _resolve_dep(namespace, source_name)
        except KeyError:
            missing.append(source_name)

    if missing:
        raise KeyError(f"Missing deps for build_alias_settings_command_deps: {', '.join(missing)}")

    return SimpleNamespace(**values)
