import asyncio
from types import SimpleNamespace

import main
import dkreminders_bot.integrations.voice_remind_flow as voice_remind_flow


def test_main_voice_remind_command_delegates_to_flow(monkeypatch):
    calls = []

    async def fake_flow(update, context, deps):
        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_voice_remind_command", fake_flow)

    update = SimpleNamespace()
    context = SimpleNamespace(args=[], user_data={})

    asyncio.run(main.voice_remind_command(update, context))

    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context

    deps = calls[0][2]
    assert hasattr(deps, "transcribe_voice_message")
    assert hasattr(deps, "_normalize_reminder_text_fallback")
    assert hasattr(deps, "NormalizedReminderMessageProxy")
    assert hasattr(deps, "remind_command")
    assert hasattr(deps, "safe_reply")


def test_voice_remind_wrapper_is_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    wrappers = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "voice_remind_command"
    ]

    assert len(wrappers) == 1

    wrapper = wrappers[0]
    wrapper_source = ast.get_source_segment(source, wrapper)

    assert "handle_voice_remind_command(update, context, _build_voice_remind_command_deps())" in wrapper_source
    assert wrapper.end_lineno - wrapper.lineno + 1 <= 3


def test_voice_remind_flow_contains_expected_paths():
    source = open("dkreminders_bot/integrations/voice_remind_flow.py").read()

    assert "async def handle_voice_remind_command(" in source
    assert "transcribe_voice_message(update, context)" in source
    assert "_normalize_reminder_text_fallback(heard_text)" in source
    assert "NormalizedReminderMessageProxy(" in source
    assert "await remind_command(proxy_update, context)" in source
    assert "Chat.PRIVATE" in source
    assert "import main" not in source
    assert "from main import" not in source


def test_voice_remind_flow_exports_handler():
    assert hasattr(voice_remind_flow, "handle_voice_remind_command")
