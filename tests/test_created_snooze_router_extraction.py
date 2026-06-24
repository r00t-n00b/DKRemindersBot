import asyncio
from types import SimpleNamespace

import created_snooze_router
import main


def test_main_created_snooze_callback_delegates_to_router(monkeypatch):
    calls = []

    async def fake_router(update, context, deps):
        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_created_snooze_callback", fake_router)

    update = SimpleNamespace(callback_query=SimpleNamespace(data="created_snooze:1:20m"))
    context = SimpleNamespace()

    asyncio.run(main.created_snooze_callback(update, context))

    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context
    assert hasattr(calls[0][2], "compute_snooze_target_time")
    assert hasattr(calls[0][2], "build_custom_date_keyboard")
    assert hasattr(calls[0][2], "build_custom_time_keyboard")


def test_created_snooze_router_module_exposes_handler():
    assert hasattr(created_snooze_router, "handle_created_snooze_callback")


def test_created_snooze_callback_wrapper_is_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    node = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "created_snooze_callback"
    ][0]

    wrapper_source = ast.get_source_segment(source, node)

    assert "handle_created_snooze_callback(update, context, _build_created_snooze_callback_deps())" in wrapper_source
    assert node.end_lineno - node.lineno + 1 <= 3


def test_created_snooze_router_contains_all_created_snooze_routes():
    import ast
    from pathlib import Path

    source = Path("created_snooze_router.py").read_text()
    tree = ast.parse(source)

    node = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "handle_created_snooze_callback"
    ][0]

    router_source = ast.get_source_segment(source, node)

    expected_routes = [
        'data.startswith("created_snooze:")',
        'data.startswith("created_snooze_cal:")',
        'data.startswith("created_snooze_caltoday:")',
        'data.startswith("created_snooze_pickdate:")',
        'data.startswith("created_snooze_pastdate:")',
        'data.startswith("created_snooze_picktime:")',
        'data.startswith("created_snooze_cancel:")',
    ]

    for route in expected_routes:
        assert route in router_source


def test_created_snooze_router_does_not_import_main():
    source = open("created_snooze_router.py").read()

    assert "import main" not in source
    assert "from main import" not in source
