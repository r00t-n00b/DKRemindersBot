from types import SimpleNamespace

import main
import remind_command_deps


def test_main_remind_command_deps_builder_delegates_to_factory(monkeypatch):
    calls = []

    def fake_factory(namespace):
        calls.append(namespace)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(main, "build_remind_command_deps", fake_factory)

    deps = main._build_remind_command_deps()

    assert deps.ok is True
    assert calls == [main.__dict__]


def test_main_remind_command_deps_builder_is_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    builders = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_build_remind_command_deps"
    ]

    assert len(builders) == 1

    builder = builders[0]
    builder_source = ast.get_source_segment(source, builder)

    assert "build_remind_command_deps(globals())" in builder_source
    assert builder.end_lineno - builder.lineno + 1 <= 2


def test_remind_command_deps_module_contains_expected_dependency_names():
    names = remind_command_deps.REMIND_COMMAND_DEP_NAMES

    assert "resolve_remind_target_and_args" in names
    assert "dispatch_remind_creation" in names
    assert "parse_with_optional_default_time" in names
    assert "normalize_plain_text_reminder_with_gemini" in names
    assert "get_chat_id_by_alias_for_user" in names
    assert "get_user_alias_chat_id_for_user" in names
    assert "safe_reply" in names


def test_remind_command_deps_module_does_not_import_main():
    source = open("remind_command_deps.py").read()

    assert "import main" not in source
    assert "from main import" not in source


def test_remind_command_deps_factory_returns_expected_values():
    namespace = {
        name: object()
        for name in remind_command_deps.REMIND_COMMAND_DEP_NAMES
    }

    deps = remind_command_deps.build_remind_command_deps(namespace)

    for name in remind_command_deps.REMIND_COMMAND_DEP_NAMES:
        assert getattr(deps, name) is namespace[name]


def test_remind_command_deps_factory_fails_on_missing_dep():
    namespace = {
        name: object()
        for name in remind_command_deps.REMIND_COMMAND_DEP_NAMES
    }
    missing = remind_command_deps.REMIND_COMMAND_DEP_NAMES[0]
    del namespace[missing]

    try:
        remind_command_deps.build_remind_command_deps(namespace)
    except KeyError as e:
        assert missing in str(e)
    else:
        raise AssertionError("Expected KeyError")
