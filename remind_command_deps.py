"""Dependency list for remind command router."""

from types import SimpleNamespace


REMIND_COMMAND_DEP_NAMES = (
    "Chat",
    "MSG_GROUP_ALIAS_PREFIX_FORBIDDEN",
    "MSG_GROUP_USERNAME_PREFIX_FORBIDDEN",
    "MSG_PARSE_DATE_TEXT_FAILED",
    "MSG_REMIND_USAGE",
    "_create_single_reminder_from_line",
    "_format_bulk_result",
    "_normalize_reminder_text_fallback",
    "add_reminder",
    "build_created_reminder_actions_keyboard",
    "create_recurring_template",
    "dispatch_remind_creation",
    "drop_optional_bulk_header",
    "extract_after_command",
    "first_token_looks_like_reminder_start",
    "format_created_recurring_reminder_text",
    "format_created_reminder_text",
    "format_recurring_human",
    "get_chat_id_by_alias_for_user",
    "get_now",
    "get_user_alias_chat_id_for_user",
    "get_user_chat_id_by_username",
    "get_user_default_time",
    "get_user_timezone_name",
    "handle_single_oneoff_reminder",
    "is_recurring_missing_dash_candidate",
    "logger",
    "looks_like_recurring",
    "msg_after_me_requires_date_and_text",
    "msg_after_target_requires_date_and_text",
    "msg_recurring_missing_dash",
    "msg_recurring_parse_failed",
    "msg_user_has_not_started_bot",
    "normalize_gemini_reminder_command_text",
    "normalize_plain_text_reminder_with_gemini",
    "parse_date_time_smart",
    "parse_recurring",
    "parse_with_optional_default_time",
    "reject_group_remind_target_prefix_if_needed",
    "resolve_remind_target_and_args",
    "safe_reply",
    "strip_first_token_from_first_line",
    "try_handle_single_recurring_reminder",
    "upsert_user_chat",
)


def build_remind_command_deps(namespace) -> SimpleNamespace:
    missing = [name for name in REMIND_COMMAND_DEP_NAMES if name not in namespace]
    if missing:
        raise KeyError(f"Missing remind command deps: {', '.join(missing)}")

    return SimpleNamespace(
        **{name: namespace[name] for name in REMIND_COMMAND_DEP_NAMES}
    )
