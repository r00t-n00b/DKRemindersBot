from datetime import date as date_cls


class DummyInlineKeyboardButton:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text = text
        self.callback_data = callback_data
        self.kwargs = kwargs


class DummyInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard
        self.keyboard = inline_keyboard


def _patch_keyboard_classes(main_module, monkeypatch):
    import keyboards

    monkeypatch.setattr(main_module, "InlineKeyboardButton", DummyInlineKeyboardButton)
    monkeypatch.setattr(main_module, "InlineKeyboardMarkup", DummyInlineKeyboardMarkup)
    monkeypatch.setattr(keyboards, "InlineKeyboardButton", DummyInlineKeyboardButton)
    monkeypatch.setattr(keyboards, "InlineKeyboardMarkup", DummyInlineKeyboardMarkup)


def _buttons(markup):
    rows = getattr(markup, "inline_keyboard", None) or getattr(markup, "keyboard", None) or []
    return [button for row in rows for button in row]


def _callback_data(markup):
    return [
        button.callback_data
        for button in _buttons(markup)
        if getattr(button, "callback_data", None) is not None
    ]


def test_calendar_keyboard_builders_are_exposed_via_main_proxy(main_module):
    import keyboards

    assert hasattr(keyboards, "build_custom_date_keyboard")
    assert hasattr(keyboards, "build_custom_time_keyboard")
    assert callable(main_module.build_custom_date_keyboard)
    assert callable(main_module.build_custom_time_keyboard)


def test_custom_date_keyboard_generates_snooze_callbacks(main_module, monkeypatch):
    _patch_keyboard_classes(main_module, monkeypatch)

    markup = main_module.build_custom_date_keyboard(
        7,
        year=2026,
        month=6,
        callback_prefix="snooze",
    )

    callbacks = set(_callback_data(markup))

    assert "snooze_pickdate:7:2026-06-30" in callbacks
    assert "snooze_cal:7:2026-05" in callbacks
    assert "snooze_caltoday:7" in callbacks
    assert "snooze_cal:7:2026-07" in callbacks
    assert "snooze_cancel:7" in callbacks


def test_custom_date_keyboard_generates_selfremind_event_callbacks(main_module, monkeypatch):
    _patch_keyboard_classes(main_module, monkeypatch)

    markup = main_module.build_custom_date_keyboard(
        7,
        year=2026,
        month=6,
        callback_prefix="selfremind_event",
    )

    callbacks = set(_callback_data(markup))

    assert "selfremind_event_pickdate:7:2026-06-30" in callbacks
    assert "selfremind_event_cal:7:2026-05" in callbacks
    assert "selfremind_event_caltoday:7" in callbacks
    assert "selfremind_event_cal:7:2026-07" in callbacks
    assert "selfremind_event_cancel:7" in callbacks


def test_custom_time_keyboard_generates_expected_time_callbacks(main_module, monkeypatch):
    _patch_keyboard_classes(main_module, monkeypatch)

    markup = main_module.build_custom_time_keyboard(
        7,
        "2026-06-23",
        callback_prefix="created_snooze",
    )

    callbacks = set(_callback_data(markup))

    assert "created_snooze_picktime:7:2026-06-23:10:00" in callbacks
    assert "created_snooze_picktime:7:2026-06-23:18:00" in callbacks
    assert "created_snooze_cancel:7" in callbacks


def test_keyboard_timezone_matches_main_timezone(main_module):
    import keyboards
    from datetime import datetime

    assert getattr(keyboards.TZ, "key", None) == getattr(main_module.TZ, "key", None)

    winter = datetime(2026, 1, 15, 12, 0)
    summer = datetime(2026, 7, 15, 12, 0)

    assert keyboards.TZ.utcoffset(winter) == main_module.TZ.utcoffset(winter)
    assert keyboards.TZ.utcoffset(summer) == main_module.TZ.utcoffset(summer)
