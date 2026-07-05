"""Alias and user settings command flows."""

from typing import Any, Dict, List, Optional, Tuple

from dkreminders_bot.ui.messages import (
    MSG_ALIASES_EMPTY,
    MSG_ALIASES_LOAD_CHAT_FAILED,
    MSG_ALIASES_LOAD_USER_FAILED,
    MSG_ALIAS_EMPTY,
    MSG_DEFAULT_TIME_NOT_SET,
    MSG_DEFAULT_TIME_PARSE_FAILED,
    MSG_DEFAULT_TIME_RESET,
    MSG_LINKCHAT_GROUP_ONLY,
    MSG_LINKCHAT_USAGE,
    MSG_LINKUSER_ALIAS_STARTS_WITH_AT,
    MSG_LINKUSER_USAGE,
    MSG_LINKUSER_USERNAME_REQUIRED,
    MSG_RENAMEALIAS_USAGE,
    MSG_UNALIAS_USAGE,
    MSG_USER_ALIAS_EMPTY,
    msg_alias_not_found,
    msg_default_time_current,
    msg_default_time_set,
    msg_linkchat_success,
    msg_linkuser_chat_alias_conflict,
    msg_linkuser_success,
    msg_linkuser_target_not_started,
    msg_renamealias_success,
    msg_unalias_deleted,
)


_DEP_NAMES = [
    "Chat",
    "clear_user_default_time",
    "delete_chat_alias",
    "delete_user_alias",
    "format_default_time_value",
    "get_all_aliases",
    "get_all_user_aliases",
    "get_chat_id_by_alias",
    "get_user_alias",
    "get_user_chat_id_by_username",
    "get_user_default_time",
    "logger",
    "parse_default_time_value",
    "parse_renamealias_args",
    "rename_chat_alias",
    "rename_user_alias",
    "safe_reply",
    "set_chat_alias_for_user",
    "set_user_alias",
    "set_user_default_time",
]


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


async def handle_linkchat_command(update, context, deps) -> None:
    _apply_deps(deps)
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    if chat.type == Chat.PRIVATE:
        await safe_reply(
            message,
            MSG_LINKCHAT_GROUP_ONLY
        )
        return

    if not context.args:
        await safe_reply(
            message,
            MSG_LINKCHAT_USAGE
        )
        return

    alias = context.args[0].strip()
    if not alias:
        await safe_reply(message, MSG_ALIAS_EMPTY)
        return

    title = chat.title or chat.username or str(chat.id)

    set_chat_alias_for_user(
        alias=alias,
        chat_id=chat.id,
        title=title,
        created_by=user.id,
    )

    await safe_reply(
        message,
        msg_linkchat_success(alias)
    )


async def handle_aliases_command(update, context, deps) -> None:
    _apply_deps(deps)
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None:
        return

    user_aliases = []
    chat_aliases = []

    try:
        for alias, chat_id in get_all_user_aliases(user.id):
            row = get_user_alias(alias, user.id) or {}
            username = row.get("username")
            if username:
                user_aliases.append(f"• {alias} -> @{username} / chat_id={chat_id}")
            else:
                user_aliases.append(f"• {alias} -> chat_id={chat_id}")
    except Exception:
        logger.exception("Не смог получить user aliases")
        await safe_reply(message, MSG_ALIASES_LOAD_USER_FAILED)
        return

    try:
        for alias, chat_id, title in get_all_aliases(user.id):
            if title:
                chat_aliases.append(f"• {alias} -> {title} / chat_id={chat_id}")
            else:
                chat_aliases.append(f"• {alias} -> chat_id={chat_id}")
    except Exception:
        logger.exception("Не смог получить chat aliases")
        await safe_reply(message, MSG_ALIASES_LOAD_CHAT_FAILED)
        return

    if not user_aliases and not chat_aliases:
        await safe_reply(
            message,
            MSG_ALIASES_EMPTY
        )
        return

    parts = ["Текущие алиасы:"]

    if user_aliases:
        parts.append("\n👤 User aliases:")
        parts.extend(user_aliases)

    if chat_aliases:
        parts.append("\n💬 Chat aliases:")
        parts.extend(chat_aliases)

    parts.append(
        "\nКоманды:\n"
        "/unalias <alias>\n"
        "/renamealias <old> -> <new>"
    )

    await safe_reply(message, "\n".join(parts))


async def handle_unalias_command(update, context, deps) -> None:
    _apply_deps(deps)
    message = update.effective_message
    if message is None:
        return

    alias = " ".join(getattr(context, "args", []) or []).strip()
    if not alias:
        await safe_reply(
            message,
            MSG_UNALIAS_USAGE
        )
        return

    user = update.effective_user
    if user is None:
        return

    deleted_user = delete_user_alias(alias, user.id)
    deleted_chat = delete_chat_alias(alias, user.id)

    if not deleted_user and not deleted_chat:
        await safe_reply(message, msg_alias_not_found(alias))
        return

    deleted_parts = []
    if deleted_user:
        deleted_parts.append("user-alias")
    if deleted_chat:
        deleted_parts.append("chat-alias")

    await safe_reply(
        message,
        msg_unalias_deleted(alias, deleted_parts)
    )


async def handle_renamealias_command(update, context, deps) -> None:
    _apply_deps(deps)
    message = update.effective_message
    if message is None:
        return

    old_alias, new_alias = parse_renamealias_args(getattr(context, "args", []) or [])
    if not old_alias or not new_alias:
        await safe_reply(
            message,
            MSG_RENAMEALIAS_USAGE
        )
        return

    try:
        user = update.effective_user
        if user is None:
            return
        
        renamed_user = rename_user_alias(old_alias, new_alias, user.id)
        renamed_chat = rename_chat_alias(old_alias, new_alias, user.id)
    except ValueError as e:
        await safe_reply(message, str(e))
        return

    if not renamed_user and not renamed_chat:
        await safe_reply(message, msg_alias_not_found(old_alias))
        return

    renamed_parts = []
    if renamed_user:
        renamed_parts.append("user-alias")
    if renamed_chat:
        renamed_parts.append("chat-alias")

    await safe_reply(
        message,
        msg_renamealias_success(old_alias, new_alias, renamed_parts)
    )


async def handle_defaulttime_command(update, context, deps) -> None:
    _apply_deps(deps)
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None:
        return

    args = list(context.args or [])

    if not args:
        current = get_user_default_time(user.id)
        if current is None:
            await safe_reply(
                message,
                MSG_DEFAULT_TIME_NOT_SET
            )
            return

        await safe_reply(
            message,
            msg_default_time_current(format_default_time_value(*current))
        )
        return

    value = args[0].strip().lower()

    if value in {"reset", "default", "off", "сброс", "сбросить"}:
        clear_user_default_time(user.id)
        await safe_reply(message, MSG_DEFAULT_TIME_RESET)
        return

    try:
        hour, minute = parse_default_time_value(value)
    except ValueError:
        await safe_reply(
            message,
            MSG_DEFAULT_TIME_PARSE_FAILED
        )
        return

    set_user_default_time(user.id, hour, minute)
    await safe_reply(
        message,
        msg_default_time_set(format_default_time_value(hour, minute))
    )


async def handle_linkuser_command(update, context, deps) -> None:
    _apply_deps(deps)
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None:
        return

    if len(context.args or []) != 2:
        await safe_reply(
            message,
            MSG_LINKUSER_USAGE
        )
        return

    alias = context.args[0].strip()
    username = context.args[1].strip()

    if not alias:
        await safe_reply(message, MSG_USER_ALIAS_EMPTY)
        return

    if alias.startswith("@"):
        await safe_reply(message, MSG_LINKUSER_ALIAS_STARTS_WITH_AT)
        return

    if not username.startswith("@") or len(username) <= 1:
        await safe_reply(message, MSG_LINKUSER_USERNAME_REQUIRED)
        return

    if get_chat_id_by_alias(alias, user.id) is not None:
        await safe_reply(message, msg_linkuser_chat_alias_conflict(alias))
        return

    target_chat_id = get_user_chat_id_by_username(username)
    if target_chat_id is None:
        await safe_reply(
            message,
            msg_linkuser_target_not_started(username)
        )
        return

    set_user_alias(
        alias=alias,
        user_id=int(target_chat_id),
        chat_id=int(target_chat_id),
        username=username.lstrip("@"),
        created_by=user.id,
    )

    await safe_reply(message, msg_linkuser_success(alias, username))
