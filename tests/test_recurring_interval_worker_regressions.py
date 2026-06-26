import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from test_worker_keyboard_invariants import DummyApp, StopWorker, _reminder

TZ = ZoneInfo("Europe/Madrid")


def test_compute_next_occurrence_interval_minutes_and_hours(main_module):
    after = datetime(2026, 6, 12, 10, 30, tzinfo=TZ)

    assert main_module.compute_next_occurrence(
        "interval",
        {"value": 30, "unit": "minutes"},
        11,
        0,
        after,
    ) == datetime(2026, 6, 12, 11, 0, tzinfo=TZ)

    assert main_module.compute_next_occurrence(
        "interval",
        {"value": 2, "unit": "hours"},
        11,
        0,
        after,
    ) == datetime(2026, 6, 12, 12, 30, tzinfo=TZ)


def test_compute_next_occurrence_interval_days_weeks_months_use_template_time(main_module):
    after = datetime(2026, 1, 31, 10, 30, tzinfo=TZ)

    assert main_module.compute_next_occurrence(
        "interval",
        {"value": 3, "unit": "days"},
        9,
        15,
        after,
    ) == datetime(2026, 2, 3, 9, 15, tzinfo=TZ)

    assert main_module.compute_next_occurrence(
        "interval",
        {"value": 2, "unit": "weeks"},
        9,
        15,
        after,
    ) == datetime(2026, 2, 14, 9, 15, tzinfo=TZ)

    assert main_module.compute_next_occurrence(
        "interval",
        {"value": 1, "unit": "months"},
        9,
        15,
        after,
    ) == datetime(2026, 2, 28, 9, 15, tzinfo=TZ)


def test_compute_next_occurrence_interval_invalid_payload_returns_none(main_module):
    after = datetime(2026, 6, 12, 10, 30, tzinfo=TZ)

    assert main_module.compute_next_occurrence(
        "interval",
        {"value": 0, "unit": "hours"},
        11,
        0,
        after,
    ) is None

    assert main_module.compute_next_occurrence(
        "interval",
        {"value": 2, "unit": "bad"},
        11,
        0,
        after,
    ) is None


def _install_one_due_recurring_worker(main_module, monkeypatch, reminder, template):
    calls = {"claim_due": 0}

    def fake_claim_due_reminders(now):
        calls["claim_due"] += 1
        if calls["claim_due"] == 1:
            return [reminder]
        raise StopWorker()

    async def fake_safe_get_chat_type(app, chat_id):
        return main_module.Chat.PRIVATE

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(main_module, "claim_due_reminders", fake_claim_due_reminders)
    monkeypatch.setattr(main_module, "reset_stale_processing_reminders", lambda now: 0)
    monkeypatch.setattr(main_module, "mark_reminder_delivery_failed", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "_safe_get_chat_type", fake_safe_get_chat_type)
    monkeypatch.setattr(main_module, "mark_reminder_sent", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "get_recurring_template", lambda template_id: template)
    monkeypatch.setattr(main_module, "build_snooze_keyboard", lambda reminder_id: ("SNOOZE", reminder_id))
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)


def test_worker_creates_next_interval_reminder_for_active_template(main_module, monkeypatch):
    app = DummyApp()

    source_reminder = _reminder(
        reminder_id=101,
        chat_id=456,
        text="drink water",
        template_id=77,
    )
    source_reminder.remind_at = datetime(2026, 6, 12, 10, 30, tzinfo=TZ)

    template = {
        "id": 77,
        "chat_id": 456,
        "text": "drink water",
        "pattern_type": "interval",
        "payload": {"value": 2, "unit": "hours"},
        "time_hour": 11,
        "time_minute": 0,
        "active": 1,
        "created_by": 123,
    }

    created = []

    def fake_add_reminder(*, chat_id, text, remind_at, created_by, template_id=None):
        created.append(
            {
                "chat_id": chat_id,
                "text": text,
                "remind_at": remind_at,
                "created_by": created_by,
                "template_id": template_id,
            }
        )
        return 999

    _install_one_due_recurring_worker(main_module, monkeypatch, source_reminder, template)
    monkeypatch.setattr(main_module, "add_reminder", fake_add_reminder)

    with pytest.raises(StopWorker):
        asyncio.run(main_module.reminders_worker(app))

    assert len(app.bot.sent) == 1
    assert len(created) == 1

    assert created[0] == {
        "chat_id": 456,
        "text": "drink water",
        "remind_at": datetime(2026, 6, 12, 12, 30, tzinfo=TZ),
        "created_by": 123,
        "template_id": 77,
    }


def test_worker_does_not_create_next_interval_reminder_for_inactive_template(main_module, monkeypatch):
    app = DummyApp()

    source_reminder = _reminder(
        reminder_id=101,
        chat_id=456,
        text="drink water",
        template_id=77,
    )
    source_reminder.remind_at = datetime(2026, 6, 12, 10, 30, tzinfo=TZ)

    template = {
        "id": 77,
        "chat_id": 456,
        "text": "drink water",
        "pattern_type": "interval",
        "payload": {"value": 2, "unit": "hours"},
        "time_hour": 11,
        "time_minute": 0,
        "active": 0,
        "created_by": 123,
    }

    created = []

    _install_one_due_recurring_worker(main_module, monkeypatch, source_reminder, template)
    monkeypatch.setattr(main_module, "add_reminder", lambda **kwargs: created.append(kwargs))

    with pytest.raises(StopWorker):
        asyncio.run(main_module.reminders_worker(app))

    assert len(app.bot.sent) == 1
    assert created == []
