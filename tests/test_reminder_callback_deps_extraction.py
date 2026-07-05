from types import SimpleNamespace

import main
import dkreminders_bot.callbacks.reminder_callback_deps as reminder_callback_deps


def test_main_reminder_callback_deps_builder_delegates_to_factory(monkeypatch):
    calls = []

    def fake_factory(namespace):
        calls.append(namespace)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(main, "build_reminder_callback_deps", fake_factory)

    deps = main._build_reminder_callback_deps()

    assert deps.ok is True
    assert calls == [main.__dict__]


def test_main_reminder_callback_deps_builder_is_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    builders = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_build_reminder_callback_deps"
    ]

    assert len(builders) == 1

    builder = builders[0]
    builder_source = ast.get_source_segment(source, builder)

    assert "build_reminder_callback_deps(globals())" in builder_source
    assert builder.end_lineno - builder.lineno + 1 <= 2


def test_reminder_callback_deps_module_contains_expected_dependency_names():
    names = reminder_callback_deps.REMINDER_CALLBACK_DEP_NAMES

    assert "handle_direct_snooze_action" in names
    assert "handle_done_callback" in names
    assert "handle_self_remind_mode" in names
    assert "handle_self_remind_event_before" in names
    assert "handle_snooze_current_month_callback" in names
    assert "parse_snooze_picktime_callback_data" in names
    assert "build_snooze_keyboard" in names
    assert "mark_reminder_acked" in names


def test_reminder_callback_deps_module_does_not_import_main():
    source = open("dkreminders_bot/callbacks/reminder_callback_deps.py").read()

    assert "import main" not in source
    assert "from main import" not in source


def test_reminder_callback_deps_factory_returns_expected_values():
    namespace = {
        name: object()
        for name in reminder_callback_deps.REMINDER_CALLBACK_DEP_NAMES
    }

    deps = reminder_callback_deps.build_reminder_callback_deps(namespace)

    for name in reminder_callback_deps.REMINDER_CALLBACK_DEP_NAMES:
        assert getattr(deps, name) is namespace[name]


def test_reminder_callback_deps_factory_fails_on_missing_dep():
    namespace = {
        name: object()
        for name in reminder_callback_deps.REMINDER_CALLBACK_DEP_NAMES
    }
    missing = reminder_callback_deps.REMINDER_CALLBACK_DEP_NAMES[0]
    del namespace[missing]

    try:
        reminder_callback_deps.build_reminder_callback_deps(namespace)
    except KeyError as e:
        assert missing in str(e)
    else:
        raise AssertionError("Expected KeyError")
