from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


class _Btn:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, keyboard):
        self.inline_keyboard = keyboard


def _flatten(markup):
    return [b for row in markup.inline_keyboard for b in row]


def test_build_snooze_keyboard_shape(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", _Btn)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", _Markup)

    markup = main_module.build_snooze_keyboard(123)

    assert hasattr(markup, "inline_keyboard")
    buttons = _flatten(markup)
    assert len(buttons) > 0

    cbs = [b.callback_data for b in buttons]

    # Все snooze-кнопки должны быть именно для reminder_id=123
    snooze_cbs = [cb for cb in cbs if cb.startswith("snooze:123:")]
    assert snooze_cbs

    # Должно быть хотя бы 2 разных варианта (например 10m/1h/...) - иначе клавиатура бессмысленна
    assert len(set(snooze_cbs)) >= 2


def test_build_custom_date_keyboard_has_days(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", _Btn)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", _Markup)

    markup = main_module.build_custom_date_keyboard(7)

    assert hasattr(markup, "inline_keyboard")
    buttons = _flatten(markup)
    assert len(buttons) > 0

    cbs = [b.callback_data for b in buttons]

    # Должны быть варианты выбора даты для reminder_id=7
    assert any(cb.startswith("snooze_pickdate:7:") for cb in cbs)

    # И должна быть хотя бы одна служебная кнопка (вперед/назад/назад/отмена - не важно как названа)
    assert any(cb.startswith("snooze_") and cb.endswith(":7") for cb in cbs)

def test_build_custom_time_keyboard_has_times(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", _Btn)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", _Markup)

    markup = main_module.build_custom_time_keyboard(7, "2025-01-01")

    buttons = _flatten(markup)
    assert any(b.callback_data.startswith("snooze_picktime:7:2025-01-01:") for b in buttons)
    assert any(b.callback_data.startswith("snooze_picktime:7:2025-01-01:") for b in buttons)