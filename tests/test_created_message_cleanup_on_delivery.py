import asyncio
from types import SimpleNamespace

import pytest

from reminders_workers import run_reminders_worker


class StopWorker(Exception):
    pass


class Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, *, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))
        return SimpleNamespace(chat_id=chat_id, message_id=9001)


class App:
    def __init__(self):
        self.bot = Bot()


def test_worker_deactivates_created_action_message_after_delivery():
    calls = []

    reminder = SimpleNamespace(
        id=123,
        chat_id=555,
        text="milk",
        remind_at=SimpleNamespace(isoformat=lambda: "2026-01-01T10:00:00+00:00"),
        template_id=None,
    )

    async def get_chat_type(app, chat_id):
        return "private"

    async def sleep(seconds):
        raise StopWorker()

    deps = SimpleNamespace(
        get_chat_type=get_chat_type,
        Chat=SimpleNamespace(PRIVATE="private"),
        add_reminder=lambda **kwargs: calls.append(("add", kwargs)),
        asyncio=SimpleNamespace(sleep=sleep),
        build_group_reminder_keyboard=lambda rid: f"group-kb:{rid}",
        build_snooze_keyboard=lambda rid: f"snooze-kb:{rid}",
        claim_due_reminders=lambda now: [reminder],
        compute_next_occurrence=lambda *args, **kwargs: None,
        delete_reminder_messages_by_kind=lambda bot, *, reminder_id, kind: calls.append(
            ("delete_kind", reminder_id, kind)
        ),
        get_due_nudges=lambda now: [],
        get_due_reminders=lambda now: [],
        get_now=lambda: "now",
        get_recurring_template=lambda template_id: None,
        increment_nudge_count=lambda rid: calls.append(("nudge", rid)),
        logger=SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            exception=lambda *args, **kwargs: None,
        ),
        mark_reminder_delivery_failed=lambda *args, **kwargs: calls.append(("failed", args, kwargs)),
        mark_reminder_sent=lambda rid, sent_at=None: calls.append(("sent", rid, sent_at)),
        register_reminder_message=lambda **kwargs: calls.append(("register", kwargs)),
        reset_stale_processing_reminders=lambda now: 0,
    )

    app = App()

    with pytest.raises(StopWorker):
        asyncio.run(run_reminders_worker(app, deps))

    assert app.bot.sent == [(555, "milk", "snooze-kb:123")]
    assert ("delete_kind", 123, "created") in calls
    assert ("sent", 123, "now") in calls
