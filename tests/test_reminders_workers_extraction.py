import asyncio
from types import SimpleNamespace

import main
import dkreminders_bot.workers.reminders_workers as reminders_workers


def test_main_reminders_worker_delegates_to_worker_module(monkeypatch):
    calls = []

    async def fake_worker(app, deps):
        calls.append((app, deps))

    monkeypatch.setattr(main, "run_reminders_worker", fake_worker)

    app = SimpleNamespace()

    asyncio.run(main.reminders_worker(app))

    assert len(calls) == 1
    assert calls[0][0] is app

    deps = calls[0][1]
    assert hasattr(deps, "claim_due_reminders")
    assert hasattr(deps, "reset_stale_processing_reminders")
    assert hasattr(deps, "mark_reminder_delivery_failed")
    assert hasattr(deps, "build_snooze_keyboard")
    assert hasattr(deps, "build_group_reminder_keyboard")
    assert hasattr(deps, "register_reminder_message")
    assert hasattr(deps, "mark_reminder_sent")
    assert hasattr(deps, "compute_next_occurrence")


def test_main_reminders_nudge_worker_delegates_to_worker_module(monkeypatch):
    calls = []

    async def fake_worker(app, deps):
        calls.append((app, deps))

    monkeypatch.setattr(main, "run_reminders_nudge_worker", fake_worker)

    app = SimpleNamespace()

    asyncio.run(main.reminders_nudge_worker(app))

    assert len(calls) == 1
    assert calls[0][0] is app

    deps = calls[0][1]
    assert hasattr(deps, "get_due_nudges")
    assert hasattr(deps, "build_snooze_keyboard")
    assert hasattr(deps, "increment_nudge_count")
    assert hasattr(deps, "register_reminder_message")
    assert hasattr(deps, "Chat")


def test_main_safe_get_chat_type_delegates_to_worker_module(monkeypatch):
    calls = []

    async def fake_safe_get_chat_type(app, chat_id):
        calls.append((app, chat_id))
        return "private"

    monkeypatch.setattr(main, "_worker_safe_get_chat_type", fake_safe_get_chat_type)

    app = SimpleNamespace()

    result = asyncio.run(main._safe_get_chat_type(app, 123))

    assert result == "private"
    assert calls == [(app, 123)]


def test_worker_wrappers_are_thin():
    import ast
    from pathlib import Path

    source = Path("main.py").read_text()
    tree = ast.parse(source)

    expected = {
        "_safe_get_chat_type": "_worker_safe_get_chat_type(app, chat_id)",
        "reminders_worker": "run_reminders_worker(app, _build_reminders_worker_deps())",
        "reminders_nudge_worker": "run_reminders_nudge_worker(app, _build_reminders_worker_deps())",
    }

    for name, call in expected.items():
        node = [
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == name
        ][0]
        wrapper_source = ast.get_source_segment(source, node)

        assert call in wrapper_source
        assert node.end_lineno - node.lineno + 1 <= 3


def test_reminders_workers_module_contains_expected_paths():
    source = open("dkreminders_bot/workers/reminders_workers.py").read()

    assert "async def _safe_get_chat_type(" in source
    assert "async def run_reminders_worker(" in source
    assert "async def run_reminders_nudge_worker(" in source

    assert "now = get_now()" in source
    assert "reset_stale_processing_reminders(now)" in source
    assert "claim_due_reminders(now)" in source
    assert "mark_reminder_delivery_failed(" in source
    assert "build_group_reminder_keyboard(r.id)" in source
    assert "build_snooze_keyboard(r.id)" in source
    assert "register_reminder_message(" in source
    assert "mark_reminder_sent(" in source
    assert "compute_next_occurrence(" in source

    assert "get_due_nudges(now)" in source
    assert "increment_nudge_count(" in source

    assert "await asyncio.sleep(10)" in source
    assert "await asyncio.sleep(30)" in source

    assert "import main" not in source
    assert "from main import" not in source


def test_reminders_workers_module_exports_expected_handlers():
    assert hasattr(reminders_workers, "_safe_get_chat_type")
    assert hasattr(reminders_workers, "run_reminders_worker")
    assert hasattr(reminders_workers, "run_reminders_nudge_worker")
