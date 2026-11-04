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



@pytest.mark.asyncio
async def test_nudge_preserves_source_reply():
    from dkreminders_bot.workers.reminders_workers import run_reminders_nudge_worker

    app = FakeApp()
    reminder = {
        "id": 7,
        "chat_id": 456,
        "text": "посмотреть фотографии",
        "source_chat_id": 456,
        "source_message_id": 77,
    }
    deps = _deps(None)
    deps.get_due_nudges = lambda now: [reminder]
    deps.increment_nudge_count = lambda rid: None

    with pytest.raises(StopWorker):
        await run_reminders_nudge_worker(app, deps)

    assert len(app.bot.sent) == 1
    sent = app.bot.sent[0]
    assert sent["reply_to_message_id"] == 77
    assert sent["allow_sending_without_reply"] is True
    assert sent["chat_id"] == 456


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [
    {},
    {"source_chat_id": None, "source_message_id": None},
    {"source_chat_id": 456, "source_message_id": None},
    {"source_chat_id": None, "source_message_id": 77},
])
async def test_nudge_without_source_has_no_reply(source):
    from dkreminders_bot.workers.reminders_workers import run_reminders_nudge_worker

    app = FakeApp()
    reminder = {
        "id": 8,
        "chat_id": 456,
        "text": "купить соль",
        **source,
    }
    deps = _deps(None)
    deps.get_due_nudges = lambda now: [reminder]
    deps.increment_nudge_count = lambda rid: None

    with pytest.raises(StopWorker):
        await run_reminders_nudge_worker(app, deps)

    assert len(app.bot.sent) == 1
    assert "reply_to_message_id" not in app.bot.sent[0]


@pytest.mark.asyncio
async def test_nudge_does_not_reply_across_chats():
    from dkreminders_bot.workers.reminders_workers import run_reminders_nudge_worker

    app = FakeApp()
    reminder = {
        "id": 9,
        "chat_id": 456,
        "text": "проверить сообщение",
        "source_chat_id": 999,
        "source_message_id": 77,
    }
    deps = _deps(None)
    deps.get_due_nudges = lambda now: [reminder]
    deps.increment_nudge_count = lambda rid: None

    with pytest.raises(StopWorker):
        await run_reminders_nudge_worker(app, deps)

    assert "reply_to_message_id" not in app.bot.sent[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("source_chat_id,source_message_id", [(456, 77), (999, 77), (None, None)])
@pytest.mark.parametrize("actions", [("20m", "custom"), ("custom", "20m")])
async def test_sqlite_delivery_nudge_and_repeated_snooze_keep_original_source(
    main_module, monkeypatch, source_chat_id, source_message_id, actions
):
    """Exercise real storage, workers, button data and callback routing together."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    m = main_module
    clock = {"now": datetime(2026, 6, 12, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))}
    monkeypatch.setattr(m, "get_now", lambda: clock["now"])
    # Lightweight Telegram UI types; keep the real keyboard builders in use.
    monkeypatch.setattr(m, "InlineKeyboardButton", lambda text, callback_data: SimpleNamespace(text=text, callback_data=callback_data))
    monkeypatch.setattr(m, "InlineKeyboardMarkup", lambda rows: SimpleNamespace(inline_keyboard=rows))

    class Bot(FakeBot):
        def __init__(self):
            super().__init__()
            self.deleted = []

        async def send_message(self, **kwargs):
            self.sent.append(kwargs)
            return SimpleNamespace(message_id=1000 + len(self.sent))

        async def delete_message(self, *, chat_id, message_id):
            self.deleted.append((chat_id, message_id))

    class Query:
        def __init__(self, data):
            self.data = data
            self.from_user = SimpleNamespace(id=42)
            self.message = SimpleNamespace(
                chat_id=456, chat=SimpleNamespace(id=456),
                message_id=1000 + len(bot.sent),
            )
            self.answers = []

        async def answer(self, text=None, show_alert=False):
            self.answers.append((text, show_alert))

        async def edit_message_text(self, text):
            pass

        async def edit_message_reply_markup(self, reply_markup=None):
            pass

    bot = Bot()
    app = SimpleNamespace(bot=bot)
    context = SimpleNamespace(bot=bot, user_data={})
    rid = m.add_reminder(
        chat_id=456, text="посмотреть фотографии", remind_at=clock["now"],
        created_by=42, source_chat_id=source_chat_id, source_message_id=source_message_id,
    )

    async def stop_sleep(_seconds):
        raise StopWorker

    async def run_once(worker):
        deps = m._build_reminders_worker_deps()
        deps.asyncio = SimpleNamespace(sleep=stop_sleep)
        with pytest.raises(StopWorker):
            await worker(app, deps)

    def assert_reply(sent):
        if source_chat_id == 456:
            assert sent["reply_to_message_id"] == source_message_id
            assert sent["allow_sending_without_reply"] is True
        else:
            assert "reply_to_message_id" not in sent

    for action in (*actions, None):
        # Deliver each newly persisted reminder, then nudge it from the DB row.
        before = len(bot.sent)
        await run_once(reminders_workers.run_reminders_worker)
        assert len(bot.sent) == before + 1
        assert_reply(bot.sent[-1])
        assert m.get_reminder(rid).delivered == 1
        clock["now"] += timedelta(minutes=21)
        due = m.get_due_nudges(clock["now"])
        assert [row["id"] for row in due] == [rid]
        assert due[0]["source_chat_id"] == source_chat_id
        assert due[0]["source_message_id"] == source_message_id
        await run_once(reminders_workers.run_reminders_nudge_worker)
        assert len(bot.sent) == before + 2
        assert_reply(bot.sent[-1])
        assert m.get_reminder_messages(rid)[-1]["kind"] == "nudge"
        if action is None:
            break

        # Click the actual nudge keyboard, including custom-picker entry.
        keyboard = bot.sent[-1]["reply_markup"].inline_keyboard
        data = next(
            button.callback_data for row in keyboard for button in row
            if button.callback_data == f"snooze:{rid}:{action}"
        )
        query = Query(data)
        await m.snooze_callback(SimpleNamespace(callback_query=query), context)
        if action == "custom":
            assert m.get_reminder(rid).acked == 0
            target = clock["now"] + timedelta(hours=1)
            query = Query(f"snooze_picktime:{rid}:{target:%Y-%m-%d}:{target:%H:%M}")
            await m.snooze_callback(SimpleNamespace(callback_query=query), context)
        assert query.answers[-1][0].startswith("Отложено до ")
        assert m.get_reminder(rid).acked == 1
        pending = m.get_active_reminders_for_chat(456)
        assert len(pending) == 1
        next_rid = pending[0]["id"]
        assert next_rid != rid
        reminder = m.get_reminder(next_rid)
        assert (reminder.source_chat_id, reminder.source_message_id) == (source_chat_id, source_message_id)
        assert reminder.template_id is None
        clock["now"] = reminder.remind_at
        rid = next_rid

    # Cleanup only touches bot notifications, never the original source.
    assert bot.deleted
    assert (source_chat_id, source_message_id) not in bot.deleted


@pytest.mark.asyncio
async def test_nudge_with_source_stays_private_only():
    app = FakeApp()
    deps = _deps(None)
    deps.get_due_nudges = lambda now: [{
        "id": 9, "chat_id": -456, "text": "проверить сообщение",
        "source_chat_id": -456, "source_message_id": 77,
    }]

    async def group_chat(app, chat_id):
        return "supergroup"

    deps.get_chat_type = group_chat
    with pytest.raises(StopWorker):
        await reminders_workers.run_reminders_nudge_worker(app, deps)
    assert app.bot.sent == []
