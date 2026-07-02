"""Timezone settings UX and helpers."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

try:
    from timezonefinder import TimezoneFinder
except Exception:
    TimezoneFinder = None

try:
    from telegram import (
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        KeyboardButton,
        ReplyKeyboardMarkup,
        ReplyKeyboardRemove,
    )
except Exception:
    class InlineKeyboardButton:
        def __init__(self, text, callback_data=None, **kwargs):
            self.text = text
            self.callback_data = callback_data
            self.kwargs = kwargs

    class InlineKeyboardMarkup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard

    class KeyboardButton:
        def __init__(self, text, request_location=False, **kwargs):
            self.text = text
            self.request_location = request_location
            self.kwargs = kwargs

    class ReplyKeyboardMarkup:
        def __init__(self, keyboard, **kwargs):
            self.keyboard = keyboard
            self.kwargs = kwargs

    class ReplyKeyboardRemove:
        def __init__(self, **kwargs):
            self.kwargs = kwargs


DEFAULT_TIMEZONE_NAME = "Europe/Madrid"

TIMEZONE_PRESETS = {
    "cet": ("🇪🇺 CET", "Europe/Madrid"),
    "moscow": ("🇷🇺 Россия / Москва", "Europe/Moscow"),
}

TZ_CALLBACK_PREFIX = "tz:"


def timezone_label(tz_name: str | None) -> str:
    if not tz_name:
        return "CET"

    if tz_name == "Europe/Madrid":
        return "CET"
    if tz_name == "Europe/Moscow":
        return "Россия / Москва"
    return str(tz_name)


def format_timezone_now(tz_name: str | None) -> str:
    tz_name = tz_name or DEFAULT_TIMEZONE_NAME
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE_NAME))
    return now.strftime("%d.%m %H:%M")


def build_timezone_picker_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📍 For mobile only: определить по геопозиции", callback_data="tz:geo")],
            [InlineKeyboardButton("🇪🇺 CET", callback_data="tz:preset:cet")],
            [InlineKeyboardButton("🇷🇺 Россия / Москва", callback_data="tz:preset:moscow")],
        ]
    )


def build_timezone_after_geo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🇪🇺 CET", callback_data="tz:preset:cet")],
            [InlineKeyboardButton("🇷🇺 Россия / Москва", callback_data="tz:preset:moscow")],
        ]
    )


def build_timezone_other_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🇪🇺 CET", callback_data="tz:preset:cet")],
            [InlineKeyboardButton("🇷🇺 Россия / Москва", callback_data="tz:preset:moscow")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="tz:back")],
        ]
    )


def build_timezone_migration_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Да, все", callback_data="tz:migrate:all")],
            [InlineKeyboardButton("Да, только одинарные", callback_data="tz:migrate:oneoff")],
            [InlineKeyboardButton("Да, только повторяющиеся", callback_data="tz:migrate:recurring")],
            [InlineKeyboardButton("Нет, ничего не надо", callback_data="tz:migrate:none")],
        ]
    )


def build_location_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Поделиться геопозицией", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def detect_timezone_from_location(latitude: float, longitude: float) -> str | None:
    if TimezoneFinder is None:
        return None

    finder = TimezoneFinder()
    return finder.timezone_at(lat=float(latitude), lng=float(longitude))


def build_first_timezone_prompt() -> str:
    return (
        "Telegram не передаёт мне твой часовой пояс автоматически, а он нужен, "
        "чтобы правильно понимать фразы вроде “завтра в 10” или “каждый день в 9”.\n\n"
        "📱 Если ты на мобильном устройстве, нажми “📍 For mobile only: определить по геопозиции” — "
        "после этого кнопка отправки геопозиции появится внизу под строкой ввода. "
        "Я сохраню только часовой пояс, координаты хранить не буду.\n\n"
        "🖥️ Если ты на десктопе, Telegram не позволит пошарить геопозицию боту. "
        "В этом случае выбери часовой пояс быстрыми кнопками под сообщением.\n\n"
        "✈️ Если потом поедешь в другую страну или захочешь изменить время, "
        "зайди в /settings и поменяй часовой пояс."
    )


def build_settings_text(
    tz_name: str | None,
    default_time_text: str | None = None,
    *,
    active_reminders_count: int | None = None,
    active_recurring_templates_count: int | None = None,
    user_alias_lines: list[str] | None = None,
    chat_alias_lines: list[str] | None = None,
) -> str:
    tz_name = tz_name or DEFAULT_TIMEZONE_NAME
    default_line = default_time_text or "10:00"
    active_count = 0 if active_reminders_count is None else int(active_reminders_count)
    recurring_count = 0 if active_recurring_templates_count is None else int(active_recurring_templates_count)
    user_alias_lines = user_alias_lines or []
    chat_alias_lines = chat_alias_lines or []

    parts = [
        "Настройки",
        "",
        f"Часовой пояс: {timezone_label(tz_name)}",
        f"Сейчас в нём: {format_timezone_now(tz_name)}",
        f"Если ты не укажешь время при постановке ремайндера, то я установлю его на {default_line}. Изменить это можно командой указанной ниже.",
        f"Запланированные напоминания: {active_count}",
        f"Активные повторяющиеся напоминания: {recurring_count}",
    ]

    if user_alias_lines or chat_alias_lines:
        parts.extend(["", "Алиасы:"])
        if user_alias_lines:
            parts.append("👤 User aliases:")
            parts.extend(user_alias_lines)
        if chat_alias_lines:
            parts.append("💬 Chat aliases:")
            parts.extend(chat_alias_lines)
    else:
        parts.extend(
            [
                "",
                "Алиасы:",
                "Тобой не было заведено ни одного алиаса. Если хочешь это сделать, воспользуйся командами ниже.",
            ]
        )

    parts.extend(
        [
            "",
            "Команды для изменения:",
            "/defaulttime 09:30 — изменить время, которое подставляется, если ты указал дату без времени",
            "/defaulttime reset — сбросить это время на 10:00",
            "/aliases — посмотреть алиасы",
            "/linkuser <alias> @username — добавить user alias",
            "/linkchat <alias> — добавить chat alias в группе",
            "/unalias <alias> — удалить алиас",
            "",
            "Часовой пояс можно поменять кнопками ниже.",
            "📱 Если ты на мобильном устройстве, нажми “📍 For mobile only: определить по геопозиции” — после этого кнопка отправки геопозиции появится внизу под строкой ввода. Я сохраню только часовой пояс, координаты хранить не буду.",
            "🖥️ Если ты на десктопе, Telegram не позволит пошарить геопозицию боту. В этом случае выбери часовой пояс быстрыми кнопками под сообщением.",
            "✈️ Если потом поедешь в другую страну или захочешь изменить время, зайди в /settings и поменяй часовой пояс.",
        ]
    )

    return "\n".join(parts)


async def _reply(message, text: str, **kwargs):
    if not message or not hasattr(message, "reply_text"):
        return None
    result = message.reply_text(text, **kwargs)
    if hasattr(result, "__await__"):
        return await result
    return result


async def _edit_or_reply(query, text: str, **kwargs) -> None:
    try:
        result = query.edit_message_text(text, **kwargs)
        if hasattr(result, "__await__"):
            await result
        return
    except Exception as e:
        # Telegram raises "message is not modified" when the user presses
        # a button that would render the same screen again. In that case
        # do nothing instead of posting a duplicate message.
        if "not modified" in str(e).lower():
            return

    message = getattr(query, "message", None)
    await _reply(message, text, **kwargs)


async def _delete_saved_location_prompt(update, context) -> None:
    prompt_id = context.user_data.pop("timezone_location_prompt_message_id", None)
    if not prompt_id:
        return

    query = getattr(update, "callback_query", None)
    message = getattr(query, "message", None) if query is not None else None
    if message is None:
        message = getattr(update, "effective_message", None)

    chat_id = getattr(message, "chat_id", None)
    if chat_id is None:
        chat = getattr(message, "chat", None)
        chat_id = getattr(chat, "id", None)

    bot = getattr(context, "bot", None)
    if bot is None or chat_id is None:
        return

    try:
        result = bot.delete_message(chat_id=chat_id, message_id=prompt_id)
        if hasattr(result, "__await__"):
            await result
    except Exception:
        pass


async def _resume_pending_plain_text_reminder(update, context, deps) -> bool:
    raw_text = context.user_data.get("pending_plain_text_reminder_after_timezone")
    if not raw_text:
        return False

    handler = getattr(deps, "plain_text_remind_command", None)
    if not callable(handler):
        return False

    query = getattr(update, "callback_query", None)
    message = getattr(query, "message", None) if query is not None else None
    if message is None:
        message = getattr(update, "effective_message", None)
    if message is None:
        return False

    chat = getattr(message, "chat", None)
    if chat is None:
        chat = SimpleNamespace(
            id=getattr(message, "chat_id", None),
            type="private",
        )

    proxy_message = SimpleNamespace(
        text=raw_text,
        reply_text=getattr(message, "reply_text", None),
    )
    proxy_update = SimpleNamespace(
        effective_chat=chat,
        effective_message=proxy_message,
        effective_user=getattr(update, "effective_user", None),
        message=proxy_message,
    )

    await handler(proxy_update, context)
    context.user_data.pop("pending_plain_text_reminder_after_timezone", None)
    return True


def _load_settings_alias_lines(user_id: int, deps) -> tuple[list[str], list[str]]:
    user_alias_lines: list[str] = []
    chat_alias_lines: list[str] = []

    if hasattr(deps, "get_all_user_aliases"):
        for alias, chat_id in deps.get_all_user_aliases(user_id):
            row = {}
            if hasattr(deps, "get_user_alias"):
                row = deps.get_user_alias(alias, user_id) or {}
            username = row.get("username") if isinstance(row, dict) else None
            if username:
                user_alias_lines.append(f"• {alias} -> @{username} / chat_id={chat_id}")
            else:
                user_alias_lines.append(f"• {alias} -> chat_id={chat_id}")

    if hasattr(deps, "get_all_aliases"):
        for alias, chat_id, title in deps.get_all_aliases(user_id):
            if title:
                chat_alias_lines.append(f"• {alias} -> {title} / chat_id={chat_id}")
            else:
                chat_alias_lines.append(f"• {alias} -> chat_id={chat_id}")

    return user_alias_lines, chat_alias_lines


async def handle_settings_command(update, context, deps) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    if hasattr(deps, "get_user_timezone_name_raw") and deps.get_user_timezone_name_raw(user.id) is None:
        await _reply(
            message,
            build_first_timezone_prompt(),
            reply_markup=build_timezone_picker_keyboard(),
        )
        return

    tz_name = deps.get_user_timezone_name(user.id)
    default_time = None
    if hasattr(deps, "get_user_default_time"):
        value = deps.get_user_default_time(user.id)
        if value:
            default_time = f"{value[0]:02d}:{value[1]:02d}"

    active_count = 0
    if hasattr(deps, "count_active_reminders_for_user"):
        active_count = deps.count_active_reminders_for_user(user.id)

    recurring_count = 0
    if hasattr(deps, "count_active_recurring_templates_for_user"):
        recurring_count = deps.count_active_recurring_templates_for_user(user.id)

    user_alias_lines, chat_alias_lines = _load_settings_alias_lines(user.id, deps)

    await _reply(
        message,
        build_settings_text(
            tz_name,
            default_time,
            active_reminders_count=active_count,
            active_recurring_templates_count=recurring_count,
            user_alias_lines=user_alias_lines,
            chat_alias_lines=chat_alias_lines,
        ),
        reply_markup=build_timezone_picker_keyboard(),
    )


async def _after_timezone_changed(update, context, deps, *, old_tz: str, new_tz: str) -> None:
    user = update.effective_user
    if user is None:
        return

    active_count = deps.count_active_reminders_for_user(user.id)
    if active_count <= 0:
        return

    context.user_data["pending_timezone_migration"] = {
        "old_tz": old_tz,
        "new_tz": new_tz,
    }

    message = None
    query = getattr(update, "callback_query", None)
    if query is not None:
        message = getattr(query, "message", None)
    if message is None:
        message = update.effective_message

    await _reply(
        message,
        (
            "Ты поменял часовой пояс.\n\n"
            f"У тебя есть активные напоминания: {active_count}.\n\n"
            "Перенести их в новый часовой пояс?\n\n"
            "Перенести = оставить то же локальное время, но использовать новый часовой пояс.\n"
            "Например, 09:00 CET станет 09:00 Россия / Москва."
        ),
        reply_markup=build_timezone_migration_keyboard(),
    )


async def handle_timezone_callback(update, context, deps) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return

    data = query.data or ""

    if data == "tz:geo":
        await query.answer("На мобильном устройстве кнопка появится под строкой ввода")
        await _edit_or_reply(
            query,
            (
                "📱 Если ты на мобильном устройстве, нажми кнопку под строкой ввода.\n\n"
                "🖥️ Если ты на десктопе и Telegram не дал отправить геопозицию, "
                "выбери один из часовых поясов кнопками ниже или перейди на мобильное устройство.\n\n"
                "✈️ Если потом поедешь в другую страну или захочешь изменить время, "
                "зайди в /settings и поменяй часовой пояс."
            ),
            reply_markup=build_timezone_after_geo_keyboard(),
        )

        message = getattr(query, "message", None)
        sent = await _reply(
            message,
            "📱 На мобильном устройстве нажми кнопку под строкой ввода.",
            reply_markup=build_location_request_keyboard(),
        )
        message_id = getattr(sent, "message_id", None)
        if message_id is not None:
            context.user_data["timezone_location_prompt_message_id"] = message_id
        return

    if data == "tz:other":
        await query.answer()
        await _edit_or_reply(
            query,
            (
                "Выбери часовой пояс.\n\n"
                "Если нужного варианта нет, открой /settings в Telegram на телефоне "
                "и попробуй определить часовой пояс по геопозиции."
            ),
            reply_markup=build_timezone_other_keyboard(),
        )
        return

    if data == "tz:back":
        await query.answer()
        await _edit_or_reply(
            query,
            build_first_timezone_prompt(),
            reply_markup=build_timezone_picker_keyboard(),
        )
        return

    if data.startswith("tz:preset:"):
        preset_key = data.split(":", 2)[2]
        if preset_key not in TIMEZONE_PRESETS:
            await query.answer("Неизвестный часовой пояс")
            return

        _label, new_tz = TIMEZONE_PRESETS[preset_key]
        await _delete_saved_location_prompt(update, context)

        get_raw_timezone = getattr(deps, "get_user_timezone_name_raw", None)
        old_tz_raw = get_raw_timezone(user.id) if callable(get_raw_timezone) else deps.get_user_timezone_name(user.id)
        is_first_timezone = old_tz_raw is None
        old_tz = old_tz_raw or DEFAULT_TIMEZONE_NAME

        if old_tz == new_tz and not is_first_timezone:
            await query.answer("Уже выбран")
            await _edit_or_reply(
                query,
                (
                    f"Этот часовой пояс уже выбран: {timezone_label(new_tz)}\n"
                    f"Сейчас в нём: {format_timezone_now(new_tz)}\n\n"
                    "Не забудь вернуться в /settings, если полетишь в отпуск и часовой пояс изменится."
                ),
            )
            return

        deps.set_user_timezone_name(user.id, new_tz)

        await query.answer("Часовой пояс сохранён")
        await _edit_or_reply(
            query,
            (
                f"Ок, поставил часовой пояс: {timezone_label(new_tz)}\n"
                f"Сейчас в нём: {format_timezone_now(new_tz)}\n\n"
                "Не забудь вернуться в /settings, если полетишь в отпуск и часовой пояс изменится."
            ),
        )
        if old_tz != new_tz:
            await _after_timezone_changed(update, context, deps, old_tz=old_tz, new_tz=new_tz)
        await _resume_pending_plain_text_reminder(update, context, deps)
        return

    if data.startswith("tz:migrate:"):
        mode = data.split(":", 2)[2]
        pending = context.user_data.get("pending_timezone_migration") or {}
        old_tz = pending.get("old_tz")
        new_tz = pending.get("new_tz")

        if mode == "none":
            context.user_data.pop("pending_timezone_migration", None)
            await query.answer("Ок")
            await _edit_or_reply(query, "Ок, старые напоминания не трогаю.")
            return

        if mode not in {"all", "oneoff", "recurring"} or not old_tz or not new_tz:
            await query.answer("Настройка уже неактуальна")
            await _edit_or_reply(query, "Не нашёл актуальную смену часового пояса. Зайди в /settings ещё раз.")
            return

        result = deps.move_active_reminders_timezone_for_user(
            user_id=user.id,
            old_tz=old_tz,
            new_tz=new_tz,
            mode=mode,
        )
        context.user_data.pop("pending_timezone_migration", None)
        await query.answer("Готово")
        await _edit_or_reply(
            query,
            (
                "Перенёс напоминания в новый часовой пояс.\n\n"
                f"Обычных/инстансов: {result.get('reminders', 0)}\n"
                f"Повторяющихся шаблонов: {result.get('templates', 0)}"
            ),
        )
        return


async def handle_timezone_location_message(update, context, deps) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    location = getattr(message, "location", None)
    if location is None:
        return

    await _delete_saved_location_prompt(update, context)

    tz_name = detect_timezone_from_location(location.latitude, location.longitude)
    if not tz_name:
        await _reply(
            message,
            (
                "Не смог определить часовой пояс по геопозиции.\n"
                "Попробуй выбрать CET или Москву через /settings."
            ),
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    get_raw_timezone = getattr(deps, "get_user_timezone_name_raw", None)
    old_tz_raw = get_raw_timezone(user.id) if callable(get_raw_timezone) else deps.get_user_timezone_name(user.id)
    is_first_timezone = old_tz_raw is None
    old_tz = old_tz_raw or DEFAULT_TIMEZONE_NAME

    if old_tz == tz_name and not is_first_timezone:
        await _reply(
            message,
            (
                f"Этот часовой пояс уже выбран: {timezone_label(tz_name)}\n"
                f"Сейчас в нём: {format_timezone_now(tz_name)}\n\n"
                "Не забудь вернуться в /settings, если полетишь в отпуск и часовой пояс изменится."
            ),
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    deps.set_user_timezone_name(user.id, tz_name)

    await _reply(
        message,
        (
            f"Ок, поставил часовой пояс: {timezone_label(tz_name)}\n"
            f"Сейчас в нём: {format_timezone_now(tz_name)}\n\n"
            "Не забудь вернуться в /settings, если полетишь в отпуск и часовой пояс изменится."
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    if old_tz != tz_name:
        await _after_timezone_changed(update, context, deps, old_tz=old_tz, new_tz=tz_name)
    await _resume_pending_plain_text_reminder(update, context, deps)
