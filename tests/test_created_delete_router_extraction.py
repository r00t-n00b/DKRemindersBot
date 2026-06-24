
import asyncio

from types import SimpleNamespace

import created_delete_router

import main

def test_main_created_delete_callback_delegates_to_router(monkeypatch):

    calls = []

    async def fake_router(update, context, deps):

        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_created_delete_callback", fake_router)

    update = SimpleNamespace()

    context = SimpleNamespace(user_data={})

    asyncio.run(main.created_delete_callback(update, context))

    assert len(calls) == 1

    assert calls[0][0] is update

    assert calls[0][1] is context

    deps = calls[0][2]

    assert hasattr(deps, "build_recurring_delete_choice_keyboard")

    assert hasattr(deps, "delete_single_reminder_with_snapshot")

    assert hasattr(deps, "make_undo_token")

    assert hasattr(deps, "format_deleted_human")

    assert hasattr(deps, "cb_undo")

def test_created_delete_wrapper_is_thin():

    import ast

    from pathlib import Path

    source = Path("main.py").read_text()

    tree = ast.parse(source)

    wrappers = [

        node

        for node in tree.body

        if isinstance(node, ast.AsyncFunctionDef) and node.name == "created_delete_callback"

    ]

    assert len(wrappers) == 1

    wrapper = wrappers[0]

    wrapper_source = ast.get_source_segment(source, wrapper)

    assert "handle_created_delete_callback(update, context, _build_created_delete_callback_deps())" in wrapper_source

    assert wrapper.end_lineno - wrapper.lineno + 1 <= 3

def test_created_delete_router_contains_expected_branches():

    source = open("created_delete_router.py").read()

    assert "async def handle_created_delete_callback(" in source

    assert "build_recurring_delete_choice_keyboard(" in source

    assert 'context.user_data["delete_choice_source"] = "created"' in source

    assert "delete_single_reminder_with_snapshot(" in source

    assert "make_undo_token(" in source

    assert "format_deleted_human(" in source

    assert "cb_undo(token)" in source

    assert "import main" not in source

    assert "from main import" not in source

def test_created_delete_router_exports_handler():

    assert hasattr(created_delete_router, "handle_created_delete_callback")

