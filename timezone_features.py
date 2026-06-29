"""Timezone settings UX and helpers."""

from __future__ import annotations

from datetime import datetime
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
            [InlineKeyboardButton("📍 Определить по геопозиции", callback_data="tz:geo")],
            [InlineKeyboardButton("🇪🇺 CET", callback_data="tz:preset:cet")],
            [InlineKeyboardButton("🇷🇺 Россия / Москва", callback_data="tz:preset:moscow")],
            [InlineKeyboardButton("🌍 Выбрать другой", callback_data="tz:other")],
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
        "Выбери часовой пояс:\n\n"
        "Если потом поедешь в другую страну или захочешь изменить время, "
        "зайди в /settings и поменяй часовой пояс."
    )


def build_settings_text(tz_name: str | None, default_time_text: str | None = None) -> str:
    tz_name = tz_name or DEFAULT_TIMEZONE_NAME
    default_line = default_time_text or "10:00"

    return (
        "Настройки\n\n"
        f"Часовой пояс: {timezone_label(tz_name)}\n"
        f"Сейчас в нём: {format_timezone_now(tz_name)}\n"
        f"Время по умолчанию: {default_line}\n\n"
        "Если поедешь в другую страну или время изменится — поменяй часовой пояс здесь."
    )


async def _reply(message, text: str, **kwargs) -> None:
    if not message or not hasattr(message, "reply_text"):
        return
    result = message.reply_text(text, **kwargs)
    if hasattr(result, "__await__"):
        await result


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


async def handle_settings_command(update, context, deps) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    tz_name = deps.get_user_timezone_name(user.id)
    default_time = None
    if hasattr(deps, "get_user_default_time"):
        value = deps.get_user_default_time(user.id)
        if value:
            default_time = f"{value[0]:02d}:{value[1]:02d}"

    await _reply(
        message,
        build_settings_text(tz_name, default_time),
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
        await query.answer()
        await _edit_or_reply(
            query,
            (
                "Telegram Desktop не умеет отправлять геопозицию боту.\n\n"
                "Чтобы определить часовой пояс автоматически, открой /settings в Telegram на телефоне.\n\n"
                "На этом устройстве выбери часовой пояс кнопкой ниже:"
            ),
            reply_markup=build_timezone_other_keyboard(),
        )
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
        old_tz = deps.get_user_timezone_name(user.id) or DEFAULT_TIMEZONE_NAME

        if old_tz == new_tz:
            await query.answer("Уже выбран")
            await _edit_or_reply(
                query,
                (
                    f"Этот часовой пояс уже выбран: {timezone_label(new_tz)}\n"
                    f"Сейчас в нём: {format_timezone_now(new_tz)}"
                ),
                reply_markup=build_timezone_picker_keyboard(),
            )
            return

        deps.set_user_timezone_name(user.id, new_tz)

        await query.answer("Часовой пояс сохранён")
        await _edit_or_reply(
            query,
            (
                f"Ок, поставил часовой пояс: {timezone_label(new_tz)}\n"
                f"Сейчас в нём: {format_timezone_now(new_tz)}"
            ),
        )
        await _after_timezone_changed(update, context, deps, old_tz=old_tz, new_tz=new_tz)
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

    old_tz = deps.get_user_timezone_name(user.id) or DEFAULT_TIMEZONE_NAME
    deps.set_user_timezone_name(user.id, tz_name)

    await _reply(
        message,
        (
            f"Ок, поставил часовой пояс: {timezone_label(tz_name)}\n"
            f"Сейчас в нём: {format_timezone_now(tz_name)}"
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    await _after_timezone_changed(update, context, deps, old_tz=old_tz, new_tz=tz_name)
