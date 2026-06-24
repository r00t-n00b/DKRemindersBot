from types import SimpleNamespace

import delete_undo_deps
import main


def test_main_delete_undo_deps_builder_delegates_to_factory(monkeypatch):
    calls = []

    def fake_factory(namespace):
        calls.append(namespace)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(main, "build_delete_undo_callback_deps", fake_factory)

    deps = main._build_delete_undo_callback_deps()

    assert deps.ok is True
    assert calls == [main.__dict__]


def test_main_delete_undo_deps_builder_is_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    builders = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_build_delete_undo_callback_deps"
    ]

    assert len(builders) == 1

    builder = builders[0]
    builder_source = ast.get_source_segment(source, builder)

    assert "build_delete_undo_callback_deps(globals())" in builder_source
    assert builder.end_lineno - builder.lineno + 1 <= 2


def test_delete_undo_deps_module_contains_expected_dependency_names():
    names = delete_undo_deps.DELETE_UNDO_CALLBACK_DEP_NAMES

    assert "delete_single_reminder_with_snapshot" in names
    assert "delete_recurring_series_with_snapshot" in names
    assert "delete_recurring_one_instance_and_reschedule" in names
    assert "restore_deleted_snapshot" in names
    assert "format_deleted_snapshot_text" in names
    assert "format_restored_series_text" in names
    assert "format_restored_single_text" in names
    assert "build_recurring_delete_choice_keyboard" in names
    assert "cb_undo" in names


def test_delete_undo_deps_module_does_not_import_main():
    source = open("delete_undo_deps.py").read()

    assert "import main" not in source
    assert "from main import" not in source


def test_delete_undo_deps_factory_returns_expected_values():
    namespace = {
        name: object()
        for name in delete_undo_deps.DELETE_UNDO_CALLBACK_DEP_NAMES
    }

    deps = delete_undo_deps.build_delete_undo_callback_deps(namespace)

    for name in delete_undo_deps.DELETE_UNDO_CALLBACK_DEP_NAMES:
        assert getattr(deps, name) is namespace[name]


def test_delete_undo_deps_factory_fails_on_missing_dep():
    namespace = {
        name: object()
        for name in delete_undo_deps.DELETE_UNDO_CALLBACK_DEP_NAMES
    }
    missing = delete_undo_deps.DELETE_UNDO_CALLBACK_DEP_NAMES[0]
    del namespace[missing]

    try:
        delete_undo_deps.build_delete_undo_callback_deps(namespace)
    except KeyError as e:
        assert missing in str(e)
    else:
        raise AssertionError("Expected KeyError")
