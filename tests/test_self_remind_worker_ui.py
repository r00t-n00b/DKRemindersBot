import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest


TZ = ZoneInfo("Europe/Madrid")


class StopWorker(Exception):
    pass


def test_group_reminder_sent_with_self_remind_button(main_module, monkeypatch):
    m = main_module

    now = datetime(2026, 3, 1, 10, 0, tzinfo=TZ)
    monkeypatch.setattr(m, "get_now", lambda: now)
    monkeypatch.setattr(m, "Chat", SimpleNamespace(PRIVATE="private"))

    sent = []
    marked = []

    reminder = SimpleNamespace(
        id=123,
        chat_id=999,
        text="group reminder text",
        remind_at=now,
        template_id=None,
    )

    monkeypatch.setattr(m, "get_due_reminders", lambda _now: [reminder])

    async def fake_safe_get_chat_type(app, chat_id):
        assert chat_id == 999
        return "group"

    monkeypatch.setattr(m, "_safe_get_chat_type", fake_safe_get_chat_type)
    monkeypatch.setattr(m, "build_group_reminder_keyboard", lambda reminder_id: "GROUP_MARKUP")
    monkeypatch.setattr(m, "mark_reminder_sent", lambda reminder_id, sent_at=None: marked.append((reminder_id, sent_at)))
    monkeypatch.setattr(m, "get_recurring_template", lambda template_id: None)
    monkeypatch.setattr(m, "compute_next_occurrence", lambda *a, **k: None)

    async def fake_sleep(_seconds):
        raise StopWorker()

    monkeypatch.setattr(m.asyncio, "sleep", fake_sleep)

    class FakeBot:
        async def send_message(self, chat_id, text, reply_markup=None):
            sent.append((chat_id, text, reply_markup))

    app = SimpleNamespace(bot=FakeBot())

    with pytest.raises(StopWorker):
        asyncio.run(m.reminders_worker(app))

    assert sent == [(999, "group reminder text", "GROUP_MARKUP")]
    assert marked
    assert marked[0][0] == 123