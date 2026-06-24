import asyncio
from types import SimpleNamespace

import alias_settings_commands
import main
import plain_text_remind_flow


def make_update_and_context():
    message = SimpleNamespace(text="test", replies=[])
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=100, type="private"),
        effective_message=message,
        effective_user=SimpleNamespace(id=42),
        message=message,
    )
    context = SimpleNamespace(args=[], user_data={})
    return update, context


def test_main_plain_text_remind_command_delegates_to_flow(monkeypatch):
    calls = []

    async def fake_flow(update, context, deps):
        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_plain_text_remind_command", fake_flow)

    update, context = make_update_and_context()

    asyncio.run(main.plain_text_remind_command(update, context))

    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context
    assert hasattr(calls[0][2], "normalize_plain_text_reminder_with_gemini")
    assert hasattr(calls[0][2], "NormalizedReminderMessageProxy")
    assert hasattr(calls[0][2], "remind_command")


def test_main_alias_commands_delegate_to_flow(monkeypatch):
    command_to_handler = {
        "linkchat_command": "handle_linkchat_command",
        "aliases_command": "handle_aliases_command",
        "unalias_command": "handle_unalias_command",
        "renamealias_command": "handle_renamealias_command",
        "defaulttime_command": "handle_defaulttime_command",
        "linkuser_command": "handle_linkuser_command",
    }

    for command_name, handler_name in command_to_handler.items():
        calls = []

        async def fake_flow(update, context, deps, *, _calls=calls):
            _calls.append((update, context, deps))

        monkeypatch.setattr(main, handler_name, fake_flow)

        update, context = make_update_and_context()

        asyncio.run(getattr(main, command_name)(update, context))

        assert len(calls) == 1
        assert calls[0][0] is update
        assert calls[0][1] is context
        assert hasattr(calls[0][2], "safe_reply")


def test_main_wrappers_are_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    expected = {
        "plain_text_remind_command": "handle_plain_text_remind_command(update, context, _build_plain_text_remind_command_deps())",
        "linkchat_command": "handle_linkchat_command(update, context, _build_alias_settings_command_deps())",
        "aliases_command": "handle_aliases_command(update, context, _build_alias_settings_command_deps())",
        "unalias_command": "handle_unalias_command(update, context, _build_alias_settings_command_deps())",
        "renamealias_command": "handle_renamealias_command(update, context, _build_alias_settings_command_deps())",
        "defaulttime_command": "handle_defaulttime_command(update, context, _build_alias_settings_command_deps())",
        "linkuser_command": "handle_linkuser_command(update, context, _build_alias_settings_command_deps())",
    }

    for name, call in expected.items():
        node = [
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == name
        ][0]
        wrapper_source = ast.get_source_segment(source, node)

        assert call in wrapper_source
        assert node.end_lineno - node.lineno + 1 <= 3


def test_plain_text_flow_contains_expected_paths():
    source = open("plain_text_remind_flow.py").read()

    assert "async def handle_plain_text_remind_command(" in source
    assert "normalize_plain_text_reminder_with_gemini(" in source
    assert "_normalize_plain_text_reminder_locally(" in source
    assert "_normalize_plain_text_relative_reminder_locally(" in source
    assert "MSG_NOT_UNDERSTOOD_PLAIN_TEXT" in source
    assert "NormalizedReminderMessageProxy(" in source
    assert "await remind_command(proxy_update, context)" in source
    assert "import main" not in source
    assert "from main import" not in source


def test_alias_settings_flow_contains_expected_paths():
    source = open("alias_settings_commands.py").read()

    assert "async def handle_linkchat_command(" in source
    assert "async def handle_aliases_command(" in source
    assert "async def handle_unalias_command(" in source
    assert "async def handle_renamealias_command(" in source
    assert "async def handle_defaulttime_command(" in source
    assert "async def handle_linkuser_command(" in source
    assert "parse_renamealias_args(" in source
    assert "set_user_default_time(" in source
    assert "clear_user_default_time(" in source
    assert "set_user_alias(" in source
    assert "set_chat_alias_for_user(" in source
    assert "import main" not in source
    assert "from main import" not in source


def test_extracted_modules_export_expected_handlers():
    assert hasattr(plain_text_remind_flow, "handle_plain_text_remind_command")

    assert hasattr(alias_settings_commands, "handle_linkchat_command")
    assert hasattr(alias_settings_commands, "handle_aliases_command")
    assert hasattr(alias_settings_commands, "handle_unalias_command")
    assert hasattr(alias_settings_commands, "handle_renamealias_command")
    assert hasattr(alias_settings_commands, "handle_defaulttime_command")
    assert hasattr(alias_settings_commands, "handle_linkuser_command")
