from types import SimpleNamespace


class DummyInlineKeyboardButton:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class DummyInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def test_group_reminder_has_self_button(main_module, monkeypatch):
    m = main_module

    monkeypatch.setattr(m, "InlineKeyboardButton", DummyInlineKeyboardButton)
    monkeypatch.setattr(m, "InlineKeyboardMarkup", DummyInlineKeyboardMarkup)

    markup = m.build_group_reminder_keyboard(reminder_id=123)

    buttons = [
        btn.text
        for row in markup.inline_keyboard
        for btn in row
    ]
    callback_data = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
    ]

    assert "Напомнить мне лично" in buttons
    assert "selfremind:ask:123" in callback_data