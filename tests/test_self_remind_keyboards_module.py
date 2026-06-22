def _callback_data(markup):
    result = []
    rows = getattr(markup, "inline_keyboard", None)
    if rows is None:
        rows = getattr(markup, "keyboard", None)
    if rows is None:
        rows = []

    for row in rows:
        for button in row:
            data = getattr(button, "callback_data", None)
            if data is not None:
                result.append(data)

    return result


def test_self_remind_keyboard_builders_are_moved_to_keyboards_module(main_module, monkeypatch):
    import keyboards

    class DummyInlineKeyboardButton:
        def __init__(self, text, callback_data=None, **kwargs):
            self.text = text
            self.callback_data = callback_data
            self.kwargs = kwargs

    class DummyInlineKeyboardMarkup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard
            self.keyboard = inline_keyboard

    monkeypatch.setattr(main_module, "InlineKeyboardButton", DummyInlineKeyboardButton)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", DummyInlineKeyboardMarkup)
    monkeypatch.setattr(keyboards, "InlineKeyboardButton", DummyInlineKeyboardButton)
    monkeypatch.setattr(keyboards, "InlineKeyboardMarkup", DummyInlineKeyboardMarkup)

    mode_callbacks = set(_callback_data(main_module.build_self_remind_mode_keyboard(7)))
    choice_callbacks = set(_callback_data(main_module.build_self_remind_choice_keyboard(7)))
    event_callbacks = set(_callback_data(main_module.build_self_remind_event_before_keyboard(7)))

    assert {
        "selfremind:mode:7:regular",
        "selfremind:mode:7:event",
        "selfremind:cancel_personal:7",
    }.issubset(mode_callbacks)

    assert {
        "selfremind:set:7:20m",
        "selfremind:set:7:1h",
        "selfremind:set:7:3h",
        "selfremind:set:7:tomorrow11",
        "selfremind:set:7:nextmon",
        "selfremind:set:7:custom",
        "selfremind:back:7",
    }.issubset(choice_callbacks)

    assert {
        "selfremind:event_before:7:1d",
        "selfremind:event_before:7:10h",
        "selfremind:event_before:7:3h",
        "selfremind:event_before:7:1h",
        "selfremind:event_before:7:20m",
        "selfremind:event_custom:7",
        "selfremind:back:7",
    }.issubset(event_callbacks)
