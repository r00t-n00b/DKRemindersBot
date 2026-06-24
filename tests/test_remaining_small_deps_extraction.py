import ast
import builtins
import importlib
from pathlib import Path
from types import SimpleNamespace

import main


SPECS = [
    ("_build_alias_settings_command_deps", "alias_settings_deps", "build_alias_settings_command_deps", "ALIAS_SETTINGS_COMMAND_DEP_SPECS"),
    ("_build_voice_transcription_deps", "voice_transcription_deps", "build_voice_transcription_deps", "VOICE_TRANSCRIPTION_DEP_SPECS"),
    ("_build_reminder_text_normalization_deps", "reminder_text_normalization_deps", "build_reminder_text_normalization_deps", "REMINDER_TEXT_NORMALIZATION_DEP_SPECS"),
    ("_build_voice_remind_command_deps", "voice_remind_deps", "build_voice_remind_command_deps", "VOICE_REMIND_COMMAND_DEP_SPECS"),
    ("_build_plain_text_remind_command_deps", "plain_text_remind_deps", "build_plain_text_remind_command_deps", "PLAIN_TEXT_REMIND_COMMAND_DEP_SPECS"),
    ("_build_list_command_deps", "list_command_deps", "build_list_command_deps", "LIST_COMMAND_DEP_SPECS"),
    ("_build_created_delete_callback_deps", "created_delete_deps", "build_created_delete_callback_deps", "CREATED_DELETE_CALLBACK_DEP_SPECS"),
    ("_build_reminders_worker_deps", "reminders_worker_deps", "build_reminders_worker_deps", "REMINDERS_WORKER_DEP_SPECS"),
]


def test_remaining_small_deps_builders_are_thin():
    source = Path("main.py").read_text()
    tree = ast.parse(source)

    for builder_name, _module_name, factory_name, _tuple_name in SPECS:
        matches = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == builder_name
        ]

        assert len(matches) == 1

        builder = matches[0]
        builder_source = ast.get_source_segment(source, builder)

        assert f"return {factory_name}(globals())" in builder_source
        assert builder.end_lineno - builder.lineno + 1 <= 2


def test_remaining_small_deps_factories_are_imported_in_main():
    main_source = Path("main.py").read_text()

    for _builder_name, module_name, factory_name, _tuple_name in SPECS:
        assert f"from {module_name} import {factory_name}" in main_source


def test_remaining_small_deps_modules_do_not_import_main():
    for _builder_name, module_name, _factory_name, _tuple_name in SPECS:
        source = Path(f"{module_name}.py").read_text()

        assert "import main" not in source
        assert "from main import" not in source


def test_remaining_small_deps_factories_return_expected_values():
    for _builder_name, module_name, factory_name, tuple_name in SPECS:
        module = importlib.import_module(module_name)
        dep_specs = getattr(module, tuple_name)
        factory = getattr(module, factory_name)

        namespace = {}
        for _attr_name, source_name in dep_specs:
            if hasattr(builtins, source_name):
                continue
            namespace[source_name] = object()

        deps = factory(namespace)

        for attr_name, source_name in dep_specs:
            expected = getattr(builtins, source_name) if hasattr(builtins, source_name) else namespace[source_name]
            assert getattr(deps, attr_name) is expected


def test_remaining_small_deps_factories_fail_on_missing_non_builtin_dep():
    for _builder_name, module_name, factory_name, tuple_name in SPECS:
        module = importlib.import_module(module_name)
        dep_specs = getattr(module, tuple_name)
        factory = getattr(module, factory_name)

        namespace = {}
        missing_name = None

        for _attr_name, source_name in dep_specs:
            if hasattr(builtins, source_name):
                continue
            if missing_name is None:
                missing_name = source_name
                continue
            namespace[source_name] = object()

        if missing_name is None:
            continue

        try:
            factory(namespace)
        except KeyError as e:
            assert missing_name in str(e)
        else:
            raise AssertionError(f"Expected KeyError for {module_name}")


def test_remaining_small_deps_main_builders_delegate_to_factories(monkeypatch):
    for builder_name, _module_name, factory_name, _tuple_name in SPECS:
        calls = []

        def fake_factory(namespace):
            calls.append(namespace)
            return SimpleNamespace(ok=True)

        monkeypatch.setattr(main, factory_name, fake_factory)

        deps = getattr(main, builder_name)()

        assert deps.ok is True
        assert calls == [main.__dict__]
