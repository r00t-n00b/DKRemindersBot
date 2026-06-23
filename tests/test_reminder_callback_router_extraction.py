import asyncio
from types import SimpleNamespace

import main
import reminder_callback_router


def test_main_snooze_callback_delegates_to_router(monkeypatch):
    calls = []

    async def fake_router(update, context, deps):
        calls.append((update, context, deps))

    monkeypatch.setattr(main, "handle_reminder_callback", fake_router)

    update = SimpleNamespace(callback_query=SimpleNamespace(data="noop"))
    context = SimpleNamespace()

    asyncio.run(main.snooze_callback(update, context))

    assert len(calls) == 1
    assert calls[0][0] is update
    assert calls[0][1] is context
    assert hasattr(calls[0][2], "handle_noop_callback")


def test_router_module_exposes_callback_handler():
    assert hasattr(reminder_callback_router, "handle_reminder_callback")
