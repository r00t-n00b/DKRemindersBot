"""Alias and user settings command flows."""

from typing import Any, Dict, List, Optional, Tuple


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
            "Команду /linkchat нужно вызывать в групповом чате, который хочешь привязать."
        )
        return

    if not context.args:
        await safe_reply(
            message,
            "Формат: /linkchat alias\nНапример: /linkchat football"
        )
        return

    alias = context.args[0].strip()
    if not alias:
        await safe_reply(message, "Alias не должен быть пустым.")
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
        f"Ок, запомнил этот чат как '{alias}' для тебя.\n"
        f"Теперь в личке можно писать:\n"
        f"напомни {alias} 28.11 12:00 завтра футбол\n"
        f"или командой:\n"
        f"/remind {alias} 28.11 12:00 - завтра футбол"
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
        await safe_reply(message, "Не смог получить user-aliases.")
        return

    try:
        for alias, chat_id, title in get_all_aliases(user.id):
            if title:
                chat_aliases.append(f"• {alias} -> {title} / chat_id={chat_id}")
            else:
                chat_aliases.append(f"• {alias} -> chat_id={chat_id}")
    except Exception:
        logger.exception("Не смог получить chat aliases")
        await safe_reply(message, "Не смог получить chat-aliases.")
        return

    if not user_aliases and not chat_aliases:
        await safe_reply(
            message,
            "Алиасов пока нет.\n\n"
            "Создать chat-alias: /linkchat football\n"
            "Создать user-alias: /linkuser Наташа @username"
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
            "Использование: /unalias <alias>\n"
            "Пример: /unalias Наташа"
        )
        return

    user = update.effective_user
    if user is None:
        return

    deleted_user = delete_user_alias(alias, user.id)
    deleted_chat = delete_chat_alias(alias, user.id)

    if not deleted_user and not deleted_chat:
        await safe_reply(message, f"Alias '{alias}' не найден.")
        return

    deleted_parts = []
    if deleted_user:
        deleted_parts.append("user-alias")
    if deleted_chat:
        deleted_parts.append("chat-alias")

    await safe_reply(
        message,
        f"Удалил alias '{alias}' из: {', '.join(deleted_parts)}."
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
            "Использование: /renamealias <old> -> <new>\n"
            "Пример: /renamealias Наташа -> Натали"
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
        await safe_reply(message, f"Alias '{old_alias}' не найден.")
        return

    renamed_parts = []
    if renamed_user:
        renamed_parts.append("user-alias")
    if renamed_chat:
        renamed_parts.append("chat-alias")

    await safe_reply(
        message,
        f"Переименовал '{old_alias}' -> '{new_alias}' в: {', '.join(renamed_parts)}."
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
                "Время по умолчанию не задано. Для напоминаний без явно указанного времени бот использует 10:00.\n\n"
                "Поставить: /defaulttime 09:30\n"
                "Сбросить: /defaulttime reset"
            )
            return

        await safe_reply(
            message,
            f"Текущее время по умолчанию: {format_default_time_value(*current)}\n\n"
            "Изменить: /defaulttime 09:30\n"
            "Сбросить: /defaulttime reset"
        )
        return

    value = args[0].strip().lower()

    if value in {"reset", "default", "off", "сброс", "сбросить"}:
        clear_user_default_time(user.id)
        await safe_reply(message, "Ок, сбросил время по умолчанию. Теперь для напоминаний без явно указанного времени бот снова использует 10:00.")
        return

    try:
        hour, minute = parse_default_time_value(value)
    except ValueError:
        await safe_reply(
            message,
            "Не понял время. Формат: /defaulttime 09:30"
        )
        return

    set_user_default_time(user.id, hour, minute)
    await safe_reply(
        message,
        f"Ок, время по умолчанию: {format_default_time_value(hour, minute)}."
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
            "Формат:\n/linkuser alias @username\n\nПример:\n/linkuser misha @friend"
        )
        return

    alias = context.args[0].strip()
    username = context.args[1].strip()

    if not alias:
        await safe_reply(message, "Alias не может быть пустым.")
        return

    if alias.startswith("@"):
        await safe_reply(message, "Alias не должен начинаться с @. Напиши, например: /linkuser misha @friend")
        return

    if not username.startswith("@") or len(username) <= 1:
        await safe_reply(message, "Вторым аргументом нужен @username. Пример: /linkuser misha @friend")
        return

    if get_chat_id_by_alias(alias, user.id) is not None:
        await safe_reply(message, f"Alias '{alias}' уже занят chat-alias. Выбери другое имя.")
        return

    target_chat_id = get_user_chat_id_by_username(username)
    if target_chat_id is None:
        await safe_reply(
            message,
            f"Я пока не могу написать {username}, потому что он/она не нажимал(а) Start у бота."
        )
        return

    set_user_alias(
        alias=alias,
        user_id=int(target_chat_id),
        chat_id=int(target_chat_id),
        username=username.lstrip("@"),
        created_by=user.id,
    )

    await safe_reply(message, f"Ок, alias '{alias}' теперь указывает на {username}.")
