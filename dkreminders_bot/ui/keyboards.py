"""Inline keyboard builders for Telegram reminder UI."""
from dkreminders_bot.utils.time_utils import BOT_TZ, aware_now

from calendar import monthrange
from datetime import date, datetime

from typing import List, Optional

TZ = BOT_TZ

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

from dkreminders_bot.callbacks.callback_contracts import (
    cb_created_snooze,
    cb_created_snooze_custom,
    cb_del,
    cb_del_cancel,
    cb_del_one,
    cb_del_series,
    cb_done,
    cb_selfremind_ask,
    cb_selfremind_back,
    cb_selfremind_cancel_personal,
    cb_selfremind_event_before,
    cb_selfremind_event_custom,
    cb_selfremind_mode,
    cb_selfremind_set,
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

def build_self_remind_mode_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                "📅 Обычное напоминание",
                callback_data=cb_selfremind_mode(reminder_id, "regular"),
            ),
        ],
        [
            InlineKeyboardButton(
                '⏰ Напоминание "до события"',
                callback_data=cb_selfremind_mode(reminder_id, "event"),
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Я передумал, напоминание не нужно",
                callback_data=cb_selfremind_cancel_personal(reminder_id),
            ),
        ],
    ]
    return InlineKeyboardMarkup(buttons)

def build_self_remind_choice_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("⏰ +20 минут", callback_data=cb_selfremind_set(reminder_id, "20m")),
            InlineKeyboardButton("⏰ +1 час", callback_data=cb_selfremind_set(reminder_id, "1h")),
        ],
        [
            InlineKeyboardButton("⏰ +3 часа", callback_data=cb_selfremind_set(reminder_id, "3h")),
            InlineKeyboardButton("📅 Завтра (10:00)", callback_data=cb_selfremind_set(reminder_id, "tomorrow11")),
        ],
        [
            InlineKeyboardButton("📅 Следующий понедельник (10:00)", callback_data=cb_selfremind_set(reminder_id, "nextmon")),
            InlineKeyboardButton("📝 Кастом", callback_data=cb_selfremind_set(reminder_id, "custom")),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data=cb_selfremind_back(reminder_id)),
        ],
    ]
    return InlineKeyboardMarkup(buttons)

def build_self_remind_event_before_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("📅 За сутки", callback_data=cb_selfremind_event_before(reminder_id, "1d")),
            InlineKeyboardButton("⏰ За 10 часов", callback_data=cb_selfremind_event_before(reminder_id, "10h")),
        ],
        [
            InlineKeyboardButton("⏰ За 3 часа", callback_data=cb_selfremind_event_before(reminder_id, "3h")),
            InlineKeyboardButton("⏰ За 1 час", callback_data=cb_selfremind_event_before(reminder_id, "1h")),
        ],
        [
            InlineKeyboardButton("⏰ За 20 минут", callback_data=cb_selfremind_event_before(reminder_id, "20m")),
            InlineKeyboardButton("📝 Кастом", callback_data=cb_selfremind_event_custom(reminder_id)),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data=cb_selfremind_back(reminder_id)),
        ],
    ]
    return InlineKeyboardMarkup(buttons)

def build_custom_date_keyboard(
    reminder_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    callback_prefix: str = "snooze",
):
    """
    Красивый календарь на месяц:
    - Заголовок "Январь 2026"
    - Ряд дней недели
    - Сетка дней 7x6
    - Навигация prev/next месяц
    - Today и Cancel
    """
    today = aware_now(TZ).date()

    if year is None or month is None:
        year = today.year
        month = today.month

    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    month_names = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
    }
    title = f"{month_names.get(month, str(month))} {year}"

    first_weekday, days_in_month = monthrange(year, month)
    start_offset = first_weekday

    def _btn(text: str, cb: str):
        return InlineKeyboardButton(text=text, callback_data=cb)

    def _noop(text: str):
        return InlineKeyboardButton(text=text, callback_data="noop")

    keyboard: list[list[InlineKeyboardButton]] = [
        [_noop(title)],
        [_noop("Пн"), _noop("Вт"), _noop("Ср"), _noop("Чт"), _noop("Пт"), _noop("Сб"), _noop("Вс")],
    ]

    cells: list[InlineKeyboardButton] = []

    for _ in range(start_offset):
        cells.append(_noop(" "))

    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        iso = d.isoformat()

        label = str(day)
        if d == today:
            label = f"·{day}·"

        if d < today:
            cells.append(_btn(label, f"{callback_prefix}_pastdate:{reminder_id}:{iso}"))
        else:
            cells.append(_btn(label, f"{callback_prefix}_pickdate:{reminder_id}:{iso}"))

    while len(cells) % 7 != 0:
        cells.append(_noop(" "))

    while len(cells) < 42:
        cells.append(_noop(" "))

    for i in range(0, 42, 7):
        keyboard.append(cells[i:i + 7])

    prev_year = year
    prev_month = month - 1
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1

    next_year = year
    next_month = month + 1
    if next_month == 13:
        next_month = 1
        next_year += 1

    keyboard.append(
        [
            _btn("◀", f"{callback_prefix}_cal:{reminder_id}:{prev_year:04d}-{prev_month:02d}"),
            _btn("Today", f"{callback_prefix}_caltoday:{reminder_id}"),
            _btn("▶", f"{callback_prefix}_cal:{reminder_id}:{next_year:04d}-{next_month:02d}"),
        ]
    )

    keyboard.append([_btn("Cancel", f"{callback_prefix}_cancel:{reminder_id}")])

    return InlineKeyboardMarkup(keyboard)

from datetime import datetime, date

def build_custom_time_keyboard(reminder_id: int, date_str: str, callback_prefix: str = "snooze"):
    """
    Красивый выбор времени:
    - Заголовок "Время - 02.02.2026"
    - Сетка кнопок времени
    - Back (назад в календарь выбранного месяца)
    - Cancel
    """
    try:
        y, m, d = map(int, date_str.split("-"))
        chosen = date(y, m, d)
    except Exception:
        chosen = aware_now(TZ).date()

    def _btn(text: str, cb: str):
        return InlineKeyboardButton(text=text, callback_data=cb)

    def _noop(text: str):
        return InlineKeyboardButton(text=text, callback_data="noop")

    title = chosen.strftime("Время - %d.%m.%Y")

    keyboard: list[list[InlineKeyboardButton]] = [
        [_noop(title)],
    ]

    times = [
        "10:00", "10:30", "11:00", "11:30",
        "12:00", "12:30", "13:00", "13:30",
        "14:00", "15:00", "16:00", "18:00",
        "20:00", "21:00", "22:00", "23:00",
    ]

    row: list[InlineKeyboardButton] = []
    for t in times:
        row.append(_btn(t, f"{callback_prefix}_picktime:{reminder_id}:{chosen.isoformat()}:{t}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append(
        [
            _btn("◀ Back", f"{callback_prefix}_cal:{reminder_id}:{chosen.year:04d}-{chosen.month:02d}"),
            _btn("Cancel", f"{callback_prefix}_cancel:{reminder_id}"),
        ]
    )

    return InlineKeyboardMarkup(keyboard)
