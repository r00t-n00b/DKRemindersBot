import asyncio
from types import SimpleNamespace

import delete_undo_router
import main


def test_main_delete_callback_delegates_to_router(monkeypatch):
    calls = []

    async def fake_router(update, context, deps):
        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_delete_callback", fake_router)

    update = SimpleNamespace(callback_query=SimpleNamespace(data="del:1"))
    context = SimpleNamespace(user_data={})

    asyncio.run(main.delete_callback(update, context))

    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context
    assert hasattr(calls[0][2], "delete_single_reminder_with_snapshot")
    assert hasattr(calls[0][2], "build_recurring_delete_choice_keyboard")


def test_main_delete_choose_callback_delegates_to_router(monkeypatch):
    calls = []

    async def fake_router(update, context, deps):
        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_delete_choose_callback", fake_router)

    update = SimpleNamespace(callback_query=SimpleNamespace(data="del_cancel:1"))
    context = SimpleNamespace(user_data={})

    asyncio.run(main.delete_choose_callback(update, context))

    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context
    assert hasattr(calls[0][2], "delete_recurring_series_with_snapshot")
    assert hasattr(calls[0][2], "delete_recurring_one_instance_and_reschedule")


def test_main_undo_callback_delegates_to_router(monkeypatch):
    calls = []

    async def fake_router(update, context, deps):
        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_undo_callback", fake_router)

    update = SimpleNamespace(callback_query=SimpleNamespace(data="undo:abc"))
    context = SimpleNamespace(user_data={})

    asyncio.run(main.undo_callback(update, context))

    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context
    assert hasattr(calls[0][2], "restore_deleted_snapshot")
    assert hasattr(calls[0][2], "format_restored_single_text")


def test_delete_undo_router_module_exposes_handlers():
    assert hasattr(delete_undo_router, "handle_delete_callback")
    assert hasattr(delete_undo_router, "handle_delete_choose_callback")
    assert hasattr(delete_undo_router, "handle_undo_callback")


def test_delete_undo_callback_wrappers_are_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    expected = {
        "delete_callback": "handle_delete_callback(update, context, _build_delete_undo_callback_deps())",
        "delete_choose_callback": "handle_delete_choose_callback(update, context, _build_delete_undo_callback_deps())",
        "undo_callback": "handle_undo_callback(update, context, _build_delete_undo_callback_deps())",
    }

    for name, call in expected.items():
        node = [
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == name
        ][0]

        wrapper_source = ast.get_source_segment(source, node)

        assert call in wrapper_source
        assert node.end_lineno - node.lineno + 1 <= 3


def test_delete_undo_router_contains_expected_routes():
    import ast
    from pathlib import Path

    source = Path("delete_undo_router.py").read_text()
    tree = ast.parse(source)

    handlers = {
        node.name: ast.get_source_segment(source, node)
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
    }

    assert 'data.startswith("del:")' in handlers["handle_delete_callback"]
    assert 'data.startswith("del_cancel:")' in handlers["handle_delete_choose_callback"]
    assert 'data.startswith("del_one:")' in handlers["handle_delete_choose_callback"]
    assert 'data.startswith("del_series:")' in handlers["handle_delete_choose_callback"]
    assert 'data.startswith("undo:")' in handlers["handle_undo_callback"]


def test_delete_undo_router_does_not_import_main():
    source = open("delete_undo_router.py").read()

    assert "import main" not in source
    assert "from main import" not in source
