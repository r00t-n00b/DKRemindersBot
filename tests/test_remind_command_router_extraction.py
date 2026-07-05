import asyncio
from types import SimpleNamespace

import main
import dkreminders_bot.commands.remind_command_router as remind_command_router


def test_main_remind_command_delegates_to_router(monkeypatch):
    calls = []

    async def fake_router(update, context, deps):
        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_remind_command", fake_router)

    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=100, type="private"),
        effective_message=SimpleNamespace(text="/remind tomorrow - milk"),
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace()

    asyncio.run(main.remind_command(update, context))

    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context
    assert hasattr(calls[0][2], "dispatch_remind_creation")
    assert hasattr(calls[0][2], "resolve_remind_target_and_args")


def test_router_module_exposes_remind_handler():
    assert hasattr(remind_command_router, "handle_remind_command")


def test_remind_command_wrapper_is_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    node = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "remind_command"
    ][0]

    remind_source = ast.get_source_segment(source, node)

    assert "handle_remind_command(update, context, _build_remind_command_deps())" in remind_source
    assert node.end_lineno - node.lineno + 1 <= 3


def test_remind_command_router_contains_expected_flow():
    import ast
    from pathlib import Path

    source = Path("dkreminders_bot/commands/remind_command_router.py").read_text()
    tree = ast.parse(source)

    node = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "handle_remind_command"
    ][0]

    router_source = ast.get_source_segment(source, node)

    required = [
        "extract_after_command(",
        "reject_group_remind_target_prefix_if_needed(",
        "is_recurring_missing_dash_candidate(",
        "resolve_remind_target_and_args(",
        "dispatch_remind_creation(",
    ]

    for fragment in required:
        assert fragment in router_source


def test_remind_command_router_does_not_import_main():
    source = open("dkreminders_bot/commands/remind_command_router.py").read()

    assert "import main" not in source
    assert "from main import" not in source
