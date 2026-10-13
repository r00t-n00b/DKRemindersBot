from types import SimpleNamespace

import pytest

from dkreminders_bot.workers import reminders_workers


class StopWorker(Exception):
    pass


class FakeBot:
    def __init__(self):
        self.sent = []

    async def get_chat(self, chat_id):
        return SimpleNamespace(id=chat_id, type="private")

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=999)


class FakeApp:
    def __init__(self):
        self.bot = FakeBot()


def _deps(reminder):
    state = {"claimed": False}

    async def get_chat_type(app, chat_id):
        return "private"

    def claim_due_reminders(now):
        if state["claimed"]:
            return []
        state["claimed"] = True
        return [reminder]

    async def stop_sleep(_seconds):
        raise StopWorker

    return SimpleNamespace(
        get_chat_type=get_chat_type,
        Chat=SimpleNamespace(PRIVATE="private"),
        add_reminder=lambda **kwargs: None,
        asyncio=SimpleNamespace(sleep=stop_sleep),
        build_group_reminder_keyboard=lambda rid: None,
        build_snooze_keyboard=lambda rid: "keyboard",
        claim_due_reminders=claim_due_reminders,
        compute_next_occurrence=lambda *args, **kwargs: None,
        delete_reminder_messages_by_kind=lambda *args, **kwargs: None,
        get_due_nudges=lambda now: [],
        get_due_reminders=lambda now: [],
        get_now=lambda: object(),
        get_recurring_template=lambda template_id: None,
        increment_nudge_count=lambda rid: None,
        logger=SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            exception=lambda *args, **kwargs: None,
        ),
        mark_reminder_delivery_failed=lambda *args, **kwargs: None,
        mark_reminder_sent=lambda *args, **kwargs: None,
        register_reminder_message=lambda **kwargs: None,
        reset_stale_processing_reminders=lambda now: 0,
    )


@pytest.mark.asyncio
async def test_worker_delivers_reply_context_as_reply_to_source():
    reminder = SimpleNamespace(
        id=1,
        chat_id=456,
        text="проверить документ",
        remind_at=SimpleNamespace(isoformat=lambda: "2026-10-13T12:00:00"),
        created_by=123,
        template_id=None,
        source_chat_id=456,
        source_message_id=77,
    )
    app = FakeApp()

    with pytest.raises(StopWorker):
        await reminders_workers.run_reminders_worker(app, _deps(reminder))

    assert app.bot.sent == [{
        "chat_id": 456,
        "text": "проверить документ",
        "reply_markup": "keyboard",
        "reply_to_message_id": 77,
        "allow_sending_without_reply": True,
    }]


@pytest.mark.asyncio
async def test_worker_delivers_normally_without_reply_source():
    reminder = SimpleNamespace(
        id=2,
        chat_id=456,
        text="купить соль",
        remind_at=SimpleNamespace(isoformat=lambda: "2026-10-13T12:00:00"),
        created_by=123,
        template_id=None,
        source_chat_id=None,
        source_message_id=None,
    )
    app = FakeApp()

    with pytest.raises(StopWorker):
        await reminders_workers.run_reminders_worker(app, _deps(reminder))

    assert app.bot.sent == [{
        "chat_id": 456,
        "text": "купить соль",
        "reply_markup": "keyboard",
    }]


@pytest.mark.asyncio
async def test_worker_deleted_source_still_delivers_reminder():
    reminder = SimpleNamespace(
        id=3,
        chat_id=456,
        text="проверить удалённый документ",
        remind_at=SimpleNamespace(isoformat=lambda: "2026-10-13T12:00:00"),
        created_by=123,
        template_id=None,
        source_chat_id=456,
        source_message_id=77,
    )

    class DeletedSourceBot(FakeBot):
        async def send_message(self, **kwargs):
            # Telegram/PTB with allow_sending_without_reply=True must still
            # deliver when the original source message no longer exists.
            assert kwargs["reply_to_message_id"] == 77
            assert kwargs["allow_sending_without_reply"] is True
            self.sent.append(kwargs)
            return SimpleNamespace(message_id=1000)

    app = FakeApp()
    app.bot = DeletedSourceBot()

    with pytest.raises(StopWorker):
        await reminders_workers.run_reminders_worker(app, _deps(reminder))

    assert len(app.bot.sent) == 1
    assert app.bot.sent[0]["text"] == "проверить удалённый документ"
