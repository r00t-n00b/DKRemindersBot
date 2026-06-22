class FakeInlineKeyboardButton:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class FakeInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _patch_keyboard_classes(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "InlineKeyboardButton", FakeInlineKeyboardButton)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", FakeInlineKeyboardMarkup)


def _button_texts_and_callbacks(markup):
    rows = getattr(markup, "inline_keyboard", markup)
    return [
        (getattr(button, "text", None), getattr(button, "callback_data", None))
        for row in rows
        for button in row
    ]


def test_created_actions_keyboard_for_one_off_reminder(main_module, monkeypatch):
    _patch_keyboard_classes(main_module, monkeypatch)
    keyboard = main_module.build_created_reminder_actions_keyboard(123, is_recurring=False)

    buttons = _button_texts_and_callbacks(keyboard)

    assert ("❌ Удалить", "created_del:123") in buttons
    assert ("⏰ Перенести", "created_resched:123") in buttons


def test_created_actions_keyboard_for_recurring_reminder_explains_delete_choice(main_module, monkeypatch):
    _patch_keyboard_classes(main_module, monkeypatch)
    keyboard = main_module.build_created_reminder_actions_keyboard(456, is_recurring=True)

    buttons = _button_texts_and_callbacks(keyboard)

    assert ("❌ Удалить ближайшее/серию", "created_del:456") in buttons
    assert ("⏰ Перенести ближайшее", "created_resched:456") in buttons


def test_recurring_delete_choice_keyboard_has_one_series_and_cancel(main_module, monkeypatch):
    _patch_keyboard_classes(main_module, monkeypatch)

    keyboard = main_module.build_recurring_delete_choice_keyboard(456, 999)
    buttons = _button_texts_and_callbacks(keyboard)

    assert ("🗑 Удалить ближайшее", "del_one:456") in buttons
    assert ("🧨 Удалить всю серию", "del_series:999") in buttons
    assert ("⬅️ Отмена", "del_cancel:456") in buttons
