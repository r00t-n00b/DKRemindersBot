import re
from types import SimpleNamespace


def test_main_registers_all_handlers(monkeypatch, main_module):
    m = main_module

    monkeypatch.setenv("BOT_TOKEN", "test-token")

    added_handlers = []

    class _FakeApplication:
        def add_handler(self, handler):
            added_handlers.append(handler)

        def run_polling(self):
            return None

    class _FakeBuilder:
        def __init__(self):
            self.post_init_callback = None
            self.post_shutdown_callback = None

        def token(self, _token):
            return self

        def post_init(self, _post_init):
            self.post_init_callback = _post_init
            return self

        def post_shutdown(self, _post_shutdown):
            self.post_shutdown_callback = _post_shutdown
            return self

        def build(self):
            return _FakeApplication()

    fake_app_cls = SimpleNamespace(builder=lambda: _FakeBuilder())
    monkeypatch.setattr(m, "Application", fake_app_cls, raising=False)

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

    monkeypatch.setattr(m, "CommandHandler", _FakeCommandHandler, raising=False)
    monkeypatch.setattr(m, "CallbackQueryHandler", _FakeCallbackQueryHandler, raising=False)
    monkeypatch.setattr(m, "MessageHandler", _FakeMessageHandler, raising=False)

    m.main()

    command_names = set()
    callback_patterns = []
    message_callbacks = set()

    for h in added_handlers:
        if hasattr(h, "commands"):
            for c in h.commands:
                command_names.add(c)
        if hasattr(h, "pattern") and h.pattern is not None:
            callback_patterns.append(h.pattern.pattern)
        if hasattr(h, "callback") and not hasattr(h, "commands") and not hasattr(h, "pattern"):
            message_callbacks.add(h.callback)

    assert {
        "start",
        "help",
        "linkchat",
        "linkuser",
        "aliases",
        "unalias",
        "renamealias",
        "remind",
        "list",
    } <= command_names

    assert m.voice_remind_command in message_callbacks
    assert m.plain_text_remind_command in message_callbacks

    assert r"^del:\d+$" in callback_patterns
    assert r"^del_(one|series):" in callback_patterns
    assert r"^undo:" in callback_patterns
    assert r"^created_del:\d+$" in callback_patterns
    assert r"^created_resched:\d+$" in callback_patterns
    assert r"^created_back:\d+$" in callback_patterns

    snooze_pattern = m.build_snooze_callback_pattern()
    assert snooze_pattern in callback_patterns

    assert "selfremind:ask:" in snooze_pattern
    assert "selfremind:back:" in snooze_pattern
    assert "selfremind:cancel_personal:" in snooze_pattern
    assert "selfremind:set:" in snooze_pattern
    assert "selfremind:mode:" in snooze_pattern
    assert "selfremind:event_before:" in snooze_pattern

    assert "snooze:" in snooze_pattern
    assert "snooze_cal:" in snooze_pattern
    assert "snooze_caltoday:" in snooze_pattern
    assert "snooze_pastdate:" in snooze_pattern
    assert "snooze_pickdate:" in snooze_pattern
    assert "snooze_picktime:" in snooze_pattern
    assert "snooze_cancel:" in snooze_pattern

    assert "noop" in snooze_pattern
    assert "done:" in snooze_pattern