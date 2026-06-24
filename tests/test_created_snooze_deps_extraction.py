from types import SimpleNamespace

import created_snooze_deps
import main


def test_main_created_snooze_deps_builder_delegates_to_factory(monkeypatch):
    calls = []

    def fake_factory(namespace):
        calls.append(namespace)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(main, "build_created_snooze_callback_deps", fake_factory)

    deps = main._build_created_snooze_callback_deps()

    assert deps.ok is True
    assert calls == [main.__dict__]


def test_main_created_snooze_deps_builder_is_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    builders = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_build_created_snooze_callback_deps"
    ]

    assert len(builders) == 1

    builder = builders[0]
    builder_source = ast.get_source_segment(source, builder)

    assert "build_created_snooze_callback_deps(globals())" in builder_source
    assert builder.end_lineno - builder.lineno + 1 <= 2


def test_created_snooze_deps_module_contains_expected_dependency_names():
    names = created_snooze_deps.CREATED_SNOOZE_CALLBACK_DEP_NAMES

    assert "_answer_created_action_reminder_missing" in names
    assert "_ensure_created_action_reminder_exists" in names
    assert "build_created_reschedule_keyboard" in names
    assert "build_created_reminder_actions_keyboard_for_reminder" in names
    assert "build_custom_date_keyboard" in names
    assert "build_custom_time_keyboard" in names
    assert "compute_snooze_target_time" in names
    assert "update_reminder_time" in names
    assert "get_user_default_time" in names


def test_created_snooze_deps_module_does_not_import_main():
    source = open("created_snooze_deps.py").read()

    assert "import main" not in source
    assert "from main import" not in source


def test_created_snooze_deps_factory_returns_expected_values():
    namespace = {
        name: object()
        for name in created_snooze_deps.CREATED_SNOOZE_CALLBACK_DEP_NAMES
    }

    deps = created_snooze_deps.build_created_snooze_callback_deps(namespace)

    for name in created_snooze_deps.CREATED_SNOOZE_CALLBACK_DEP_NAMES:
        assert getattr(deps, name) is namespace[name]


def test_created_snooze_deps_factory_fails_on_missing_dep():
    namespace = {
        name: object()
        for name in created_snooze_deps.CREATED_SNOOZE_CALLBACK_DEP_NAMES
    }
    missing = created_snooze_deps.CREATED_SNOOZE_CALLBACK_DEP_NAMES[0]
    del namespace[missing]

    try:
        created_snooze_deps.build_created_snooze_callback_deps(namespace)
    except KeyError as e:
        assert missing in str(e)
    else:
        raise AssertionError("Expected KeyError")
