from datetime import datetime
from types import SimpleNamespace

import pytest

import main
from dkreminders_bot.callbacks.self_remind_time import compute_self_remind_time
from dkreminders_bot.ui.keyboard_builder_proxy import (
    build_created_reschedule_keyboard_impl,
    build_self_remind_choice_keyboard_impl,
    build_snooze_keyboard_impl,
)


class FakeInlineKeyboardButton:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text = text
        self.callback_data = callback_data
        self.kwargs = kwargs


class FakeInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _button_texts(markup):
    return [
        button.text
        for row in markup.inline_keyboard
        for button in row
    ]


def test_compute_snooze_next_monday_uses_default_time():
    now = datetime(2026, 7, 7, 12, 0, tzinfo=main.TZ)

    actual = main.compute_snooze_target_time(
        "nextmon",
        now,
        default_time=(11, 30),
    )

    assert actual.weekday() == 0
    assert (actual.hour, actual.minute) == (11, 30)


def test_compute_snooze_tomorrow_still_uses_default_time():
    now = datetime(2026, 7, 7, 12, 0, tzinfo=main.TZ)

    actual = main.compute_snooze_target_time(
        "tomorrow",
        now,
        default_time=(11, 30),
    )

    assert actual.date().isoformat() == "2026-07-08"
    assert (actual.hour, actual.minute) == (11, 30)


def test_compute_self_remind_tomorrow_and_next_monday_use_default_time():
    now = datetime(2026, 7, 7, 12, 0, tzinfo=main.TZ)

    tomorrow = compute_self_remind_time(
        "tomorrow11",
        now,
        default_time=(9, 45),
    )
    nextmon = compute_self_remind_time(
        "nextmon",
        now,
        default_time=(9, 45),
    )

    assert tomorrow.date().isoformat() == "2026-07-08"
    assert (tomorrow.hour, tomorrow.minute) == (9, 45)
    assert nextmon.weekday() == 0
    assert (nextmon.hour, nextmon.minute) == (9, 45)


@pytest.mark.parametrize(
    "builder",
    [
        build_snooze_keyboard_impl,
        build_created_reschedule_keyboard_impl,
        build_self_remind_choice_keyboard_impl,
    ],
)
def test_quick_snooze_keyboard_labels_use_default_time(builder):
    deps = SimpleNamespace(
        InlineKeyboardButton=FakeInlineKeyboardButton,
        InlineKeyboardMarkup=FakeInlineKeyboardMarkup,
        get_reminder=lambda reminder_id: SimpleNamespace(id=reminder_id, created_by=42),
        get_user_default_time=lambda user_id: (11, 30),
        keyboard_builders=main.keyboard_builders,
    )

    markup = builder(123, deps=deps)
    texts = _button_texts(markup)

    assert "📅 Завтра (11:30)" in texts
    assert "📅 Следующий понедельник (11:30)" in texts
    assert "📅 Завтра (10:00)" not in texts
    assert "📅 Следующий понедельник (10:00)" not in texts


def test_quick_snooze_keyboard_labels_fallback_to_10_if_no_default_time():
    deps = SimpleNamespace(
        InlineKeyboardButton=FakeInlineKeyboardButton,
        InlineKeyboardMarkup=FakeInlineKeyboardMarkup,
        get_reminder=lambda reminder_id: SimpleNamespace(id=reminder_id, created_by=42),
        get_user_default_time=lambda user_id: None,
        keyboard_builders=main.keyboard_builders,
    )

    markup = build_snooze_keyboard_impl(123, deps=deps)
    texts = _button_texts(markup)

    assert "📅 Завтра (10:00)" in texts
    assert "📅 Следующий понедельник (10:00)" in texts
