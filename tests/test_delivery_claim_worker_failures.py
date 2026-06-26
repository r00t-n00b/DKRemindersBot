import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from test_worker_keyboard_invariants import StopWorker, _reminder

TZ = ZoneInfo("Europe/Madrid")


class FailingBot:
    async def send_message(self, **kwargs):
        raise RuntimeError("telegram send failed")


class DummyApp:
    def __init__(self):
        self.bot = FailingBot()


def test_worker_marks_claimed_reminder_failed_when_send_message_fails(main_module, monkeypatch):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)
    reminder = _reminder(reminder_id=123, chat_id=456, text="will fail")
    reminder.remind_at = now

    claimed = []
    failed = []
    sent = []

    def fake_claim_due_reminders(claim_now):
        claimed.append(claim_now)
        if len(claimed) == 1:
            return [reminder]
        raise StopWorker()

    async def fake_safe_get_chat_type(app, chat_id):
        return main_module.Chat.PRIVATE

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(main_module, "datetime", SimpleNamespace(now=lambda tz=None: now))
    monkeypatch.setattr(main_module, "reset_stale_processing_reminders", lambda reset_now: 0)
    monkeypatch.setattr(main_module, "claim_due_reminders", fake_claim_due_reminders)
    monkeypatch.setattr(main_module, "_safe_get_chat_type", fake_safe_get_chat_type)
    monkeypatch.setattr(main_module, "build_snooze_keyboard", lambda reminder_id: ("SNOOZE", reminder_id))
    monkeypatch.setattr(main_module, "mark_reminder_sent", lambda *args, **kwargs: sent.append((args, kwargs)))
    monkeypatch.setattr(
        main_module,
        "mark_reminder_delivery_failed",
        lambda reminder_id, error, failed_at=None, **kwargs: failed.append(
            {
                "reminder_id": reminder_id,
                "error": error,
                "failed_at": failed_at,
                "kwargs": kwargs,
            }
        ),
    )
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(StopWorker):
        asyncio.run(main_module.reminders_worker(DummyApp()))

    assert claimed == [now, now]
    assert sent == []
    assert len(failed) == 1
    assert failed[0]["reminder_id"] == 123
    assert failed[0]["error"] == "telegram send failed"
    assert failed[0]["failed_at"] == now


def test_worker_resets_stale_processing_before_claiming_due_reminders(main_module, monkeypatch):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)
    calls = []

    def fake_reset_stale_processing_reminders(reset_now):
        calls.append(("reset", reset_now))
        return 2

    def fake_claim_due_reminders(claim_now):
        calls.append(("claim", claim_now))
        raise StopWorker()

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(main_module, "datetime", SimpleNamespace(now=lambda tz=None: now))
    monkeypatch.setattr(main_module, "reset_stale_processing_reminders", fake_reset_stale_processing_reminders)
    monkeypatch.setattr(main_module, "claim_due_reminders", fake_claim_due_reminders)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(StopWorker):
        asyncio.run(main_module.reminders_worker(SimpleNamespace(bot=object())))

    assert calls == [
        ("reset", now),
        ("claim", now),
    ]
