import re
from types import SimpleNamespace


class DummyInlineKeyboardButton:
    def __init__(self, text, callback_data=None, **kwargs):
        self.text = text
        self.callback_data = callback_data
        self.kwargs = kwargs


class DummyInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _patch_keyboard_classes(m, monkeypatch):
    monkeypatch.setattr(m, "InlineKeyboardButton", DummyInlineKeyboardButton)
    monkeypatch.setattr(m, "InlineKeyboardMarkup", DummyInlineKeyboardMarkup)

    import dkreminders_bot.ui.keyboards as keyboards
    monkeypatch.setattr(keyboards, "InlineKeyboardButton", DummyInlineKeyboardButton)
    monkeypatch.setattr(keyboards, "InlineKeyboardMarkup", DummyInlineKeyboardMarkup)


def _extract_callback_data(markup):
    if markup is None:
        return []

    callback_data = []
    for row in getattr(markup, "inline_keyboard", []) or []:
        for button in row:
            data = getattr(button, "callback_data", None)
            if data is not None:
                callback_data.append(data)
    return callback_data


def _registered_callback_patterns(m, monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test-token")

    added_handlers = []

    class _FakeApplication:
        def add_handler(self, handler):
            added_handlers.append(handler)

        def run_polling(self):
            return None

    class _FakeBuilder:
        def token(self, _token):
            return self

        def post_init(self, _post_init):
            return self

        def post_shutdown(self, _post_shutdown):
            return self

        def build(self):
            return _FakeApplication()

    class _FakeCommandHandler:
        def __init__(self, command, callback):
            self.commands = [command]
            self.callback = callback

    class _FakeCallbackQueryHandler:
        def __init__(self, callback, pattern=None):
            self.callback = callback
            self.pattern = re.compile(pattern) if isinstance(pattern, str) else pattern

    class _FakeMessageHandler:
        def __init__(self, filters, callback):
            self.filters = filters
            self.callback = callback

    fake_app_cls = SimpleNamespace(builder=lambda: _FakeBuilder())

    monkeypatch.setattr(m, "Application", fake_app_cls, raising=False)
    monkeypatch.setattr(m, "CommandHandler", _FakeCommandHandler, raising=False)
    monkeypatch.setattr(m, "CallbackQueryHandler", _FakeCallbackQueryHandler, raising=False)
    monkeypatch.setattr(m, "MessageHandler", _FakeMessageHandler, raising=False)

    m.main()

    patterns = []
    for handler in added_handlers:
        pattern = getattr(handler, "pattern", None)
        if pattern is not None:
            patterns.append(pattern)

    return patterns


def _assert_all_callbacks_are_registered(callback_data, patterns):
    missing = []
    for data in sorted(set(callback_data)):
        if not any(pattern.match(data) for pattern in patterns):
            missing.append(data)

    assert missing == []


def _assert_callback_data_fit_telegram_limit(callback_data):
    too_long = []
    for data in sorted(set(callback_data)):
        size = len(data.encode("utf-8"))
        if size > 64:
            too_long.append((data, size))

    assert too_long == []


def test_generated_callback_data_are_registered_and_fit_telegram_limit(main_module, monkeypatch):
    m = main_module
    _patch_keyboard_classes(m, monkeypatch)

    patterns = _registered_callback_patterns(m, monkeypatch)

    generated = []

    generated.extend(_extract_callback_data(m.build_list_delete_keyboard(7)))
    generated.extend(_extract_callback_data(m.build_recurring_delete_choice_keyboard(123, 456)))

    generated.extend(_extract_callback_data(m.build_created_reminder_actions_keyboard(123, is_recurring=False)))
    generated.extend(_extract_callback_data(m.build_created_reminder_actions_keyboard(123, is_recurring=True)))
    generated.extend(_extract_callback_data(m.build_created_reschedule_keyboard(123)))

    generated.extend(
        _extract_callback_data(
            m.build_custom_date_keyboard(
                123,
                year=2026,
                month=6,
                callback_prefix="created_snooze",
            )
        )
    )
    generated.extend(
        _extract_callback_data(
            m.build_custom_time_keyboard(
                123,
                "2026-06-23",
                callback_prefix="created_snooze",
            )
        )
    )

    generated.extend(
        _extract_callback_data(
            m.build_custom_date_keyboard(
                123,
                year=2026,
                month=6,
                callback_prefix="snooze",
            )
        )
    )
    generated.extend(
        _extract_callback_data(
            m.build_custom_time_keyboard(
                123,
                "2026-06-23",
                callback_prefix="snooze",
            )
        )
    )

    # Callback families produced outside simple keyboard builders.
    generated.extend(
        [
            "undo:test-token",
            "created_snooze_caltoday:123",
            "created_snooze_pastdate:123",
            "snooze_caltoday:123",
            "snooze_pastdate:123",
            "noop",
            "done:123",
            "selfremind:ask:123",
            "selfremind:back:123",
            "selfremind:cancel_personal:123",
            "selfremind:set:123:1h",
            "selfremind:mode:123:event",
            "selfremind:event_before:123:1h",
        ]
    )

    _assert_all_callbacks_are_registered(generated, patterns)
    _assert_callback_data_fit_telegram_limit(generated)


def test_created_snooze_callbacks_are_not_covered_by_generic_snooze_pattern(main_module):
    m = main_module

    snooze_pattern = re.compile(m.build_snooze_callback_pattern())

    created_callbacks = [
        "created_snooze:123:1h",
        "created_snooze_cal:123:2026-06",
        "created_snooze_caltoday:123",
        "created_snooze_pastdate:123",
        "created_snooze_pickdate:123:2026-06-23",
        "created_snooze_picktime:123:2026-06-23:10:00",
        "created_snooze_cancel:123",
        "created_snooze_custom:123",
    ]

    assert not any(snooze_pattern.match(data) for data in created_callbacks)


def test_callback_prefixes_do_not_shadow_more_specific_created_snooze_handlers(main_module, monkeypatch):
    m = main_module
    patterns = [pattern.pattern for pattern in _registered_callback_patterns(m, monkeypatch)]

    created_snooze_pattern = r"^created_snooze(:|_cal:|_caltoday:|_pastdate:|_pickdate:|_picktime:|_cancel:)"
    created_snooze_custom_pattern = r"^created_snooze_custom:\d+$"

    assert created_snooze_pattern in patterns
    assert created_snooze_custom_pattern in patterns

    compiled_created_snooze = re.compile(created_snooze_pattern)
    assert not compiled_created_snooze.match("created_snooze_custom:123")
