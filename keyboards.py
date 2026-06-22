"""Inline keyboard builders for Telegram reminder UI."""

from typing import List, Optional

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
except ModuleNotFoundError:
    class InlineKeyboardButton:
        def __init__(self, text, callback_data=None, **kwargs):
            self.text = text
            self.callback_data = callback_data
            self.kwargs = kwargs

    class InlineKeyboardMarkup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard

from callback_contracts import (
    cb_created_snooze,
    cb_created_snooze_custom,
    cb_del,
    cb_del_cancel,
    cb_del_one,
    cb_del_series,
    cb_done,
    cb_selfremind_ask,
    cb_snooze,
)


def build_list_delete_keyboard(count: int) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []

    for idx in range(1, count + 1):
        row.append(
            InlineKeyboardButton(
                text=f"❌{idx}",
                callback_data=f"del:{idx}",
            )
        )
        if len(row) == 5:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(buttons)

def build_recurring_delete_choice_keyboard(reminder_id: int, template_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🗑 Удалить ближайшее", callback_data=cb_del_one(reminder_id))],
            [InlineKeyboardButton("🧨 Удалить всю серию", callback_data=f"del_series:{int(template_id)}")],
            [InlineKeyboardButton("⬅️ Отмена", callback_data=cb_del_cancel(reminder_id))],
        ]
    )

def build_created_reminder_actions_keyboard(reminder_id: int, is_recurring: bool = False) -> Optional[InlineKeyboardMarkup]:
    try:
        delete_text = "❌ Удалить ближайшее/серию" if is_recurring else "❌ Удалить"
        reschedule_text = "⏰ Перенести ближайшее" if is_recurring else "⏰ Перенести"
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(delete_text, callback_data=f"created_del:{reminder_id}"),
                    InlineKeyboardButton(reschedule_text, callback_data=f"created_resched:{reminder_id}"),
                ]
            ]
        )
    except TypeError:
        return None

def build_created_reschedule_keyboard(reminder_id: int) -> Optional[InlineKeyboardMarkup]:
    try:
        buttons: List[List[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton("⏰ +20 минут", callback_data=f"created_snooze:{reminder_id}:20m"),
                InlineKeyboardButton("⏰ +1 час", callback_data=f"created_snooze:{reminder_id}:1h"),
            ],
            [
                InlineKeyboardButton("⏰ +3 часа", callback_data=f"created_snooze:{reminder_id}:3h"),
                InlineKeyboardButton("📅 Завтра (10:00)", callback_data=f"created_snooze:{reminder_id}:tomorrow"),
            ],
            [
                InlineKeyboardButton("📅 Следующий понедельник (10:00)", callback_data=f"created_snooze:{reminder_id}:nextmon"),
                InlineKeyboardButton("📝 Кастом", callback_data=cb_created_snooze_custom(reminder_id)),
            ],
            [
                InlineKeyboardButton("⬅️ Назад", callback_data=f"created_back:{reminder_id}"),
            ],
        ]
        return InlineKeyboardMarkup(buttons)
    except TypeError:
        return None

def build_snooze_keyboard(reminder_id: int) -> Optional[InlineKeyboardMarkup]:
    try:
        buttons: List[List[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton("⏰ +20 минут", callback_data=f"snooze:{reminder_id}:20m"),
                InlineKeyboardButton("⏰ +1 час", callback_data=f"snooze:{reminder_id}:1h"),
            ],
            [
                InlineKeyboardButton("⏰ +3 часа", callback_data=f"snooze:{reminder_id}:3h"),
                InlineKeyboardButton("📅 Завтра (10:00)", callback_data=f"snooze:{reminder_id}:tomorrow"),
            ],
            [
                InlineKeyboardButton("📅 Следующий понедельник (10:00)", callback_data=f"snooze:{reminder_id}:nextmon"),
                InlineKeyboardButton("📝 Кастом", callback_data=f"snooze:{reminder_id}:custom"),
            ],
            [
                InlineKeyboardButton("✅ Mark complete", callback_data=cb_done(reminder_id)),
            ],
        ]
        return InlineKeyboardMarkup(buttons)
    except TypeError:
        return None

def build_group_reminder_keyboard(reminder_id: int) -> Optional[InlineKeyboardMarkup]:
    try:
        buttons: List[List[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    "Напомнить мне лично",
                    callback_data=cb_selfremind_ask(reminder_id),
                ),
            ],
        ]
        return InlineKeyboardMarkup(buttons)
    except TypeError:
        # В тестовой среде InlineKeyboardButton/Markup могут быть подменены на object.
        # В этом случае просто не рисуем клавиатуру, чтобы не ломать worker delivery tests.
        return None
