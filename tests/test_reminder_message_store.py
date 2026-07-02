import asyncio
from types import SimpleNamespace

import main


class Bot:
    def __init__(self, *, fail_delete=False):
        self.fail_delete = fail_delete
        self.deleted = []
        self.cleared = []

    async def delete_message(self, *, chat_id, message_id):
        if self.fail_delete:
            raise RuntimeError("delete failed")
        self.deleted.append((chat_id, message_id))

    async def edit_message_reply_markup(self, *, chat_id, message_id, reply_markup=None):
        self.cleared.append((chat_id, message_id, reply_markup))


def _insert_reminder_row(
    main_module,
    *,
    chat_id,
    text,
    created_by,
    delivered,
    acked,
):
    conn = main_module.sqlite3.connect(main_module.DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO reminders
            (chat_id, text, remind_at, created_by, created_at, delivered, template_id, acked, delivery_state)
        VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        (
            chat_id,
            text,
            "2026-01-01T10:00:00+00:00",
            created_by,
            "2026-01-01T09:00:00+00:00",
            delivered,
            acked,
            "sent" if delivered else "pending",
        ),
    )
    rid = c.lastrowid
    conn.commit()
    conn.close()
    return rid


def test_delete_old_snoozed_reminder_messages_deletes_only_prior_acked_same_chain(main_module):
    old_rid = _insert_reminder_row(
        main_module,
        chat_id=555,
        text="milk",
        created_by=42,
        delivered=1,
        acked=1,
    )
    current_rid = _insert_reminder_row(
        main_module,
        chat_id=555,
        text="milk",
        created_by=42,
        delivered=1,
        acked=0,
    )
    other_text_rid = _insert_reminder_row(
        main_module,
        chat_id=555,
        text="other",
        created_by=42,
        delivered=1,
        acked=1,
    )

    main_module.register_reminder_message(old_rid, 555, 1001, "delivery")
    main_module.register_reminder_message(current_rid, 555, 1002, "delivery")
    main_module.register_reminder_message(other_text_rid, 555, 1003, "delivery")

    bot = Bot()

    asyncio.run(
        main_module.delete_old_snoozed_reminder_messages(
            bot,
            current_reminder_id=current_rid,
            chat_id=555,
            text="milk",
            created_by=42,
        )
    )

    assert bot.deleted == [(555, 1001)]

    assert main_module.get_reminder_messages(old_rid) == []
    assert [row["message_id"] for row in main_module.get_reminder_messages(current_rid)] == [1002]
    assert [row["message_id"] for row in main_module.get_reminder_messages(other_text_rid)] == [1003]


def test_delete_old_snoozed_reminder_messages_falls_back_to_clear_keyboard(main_module):
    old_rid = _insert_reminder_row(
        main_module,
        chat_id=555,
        text="milk",
        created_by=42,
        delivered=1,
        acked=1,
    )
    current_rid = _insert_reminder_row(
        main_module,
        chat_id=555,
        text="milk",
        created_by=42,
        delivered=1,
        acked=0,
    )

    main_module.register_reminder_message(old_rid, 555, 1001, "delivery")

    bot = Bot(fail_delete=True)

    asyncio.run(
        main_module.delete_old_snoozed_reminder_messages(
            bot,
            current_reminder_id=current_rid,
            chat_id=555,
            text="milk",
            created_by=42,
        )
    )

    assert bot.deleted == []
    assert bot.cleared == [(555, 1001, None)]
    assert main_module.get_reminder_messages(old_rid) == []


def test_delete_old_snoozed_reminder_messages_drops_tracking_when_telegram_refuses_delete(main_module):
    class BadRequest(Exception):
        pass

    class BotRefusesDelete:
        def __init__(self):
            self.deleted = []
            self.cleared = []

        async def delete_message(self, *, chat_id, message_id):
            raise BadRequest("Message can't be deleted for everyone")

        async def edit_message_reply_markup(self, *, chat_id, message_id, reply_markup=None):
            self.cleared.append((chat_id, message_id, reply_markup))

    old_rid = _insert_reminder_row(
        main_module,
        chat_id=555,
        text="milk",
        created_by=42,
        delivered=1,
        acked=1,
    )
    current_rid = _insert_reminder_row(
        main_module,
        chat_id=555,
        text="milk",
        created_by=42,
        delivered=1,
        acked=0,
    )

    main_module.register_reminder_message(old_rid, 555, 1001, "delivery")

    bot = BotRefusesDelete()

    asyncio.run(
        main_module.delete_old_snoozed_reminder_messages(
            bot,
            current_reminder_id=current_rid,
            chat_id=555,
            text="milk",
            created_by=42,
        )
    )

    assert bot.cleared == []
    assert main_module.get_reminder_messages(old_rid) == []


def test_delete_old_snoozed_reminder_messages_stops_on_retry_after(main_module):
    class RetryAfter(Exception):
        pass

    class BotRetryAfter:
        def __init__(self):
            self.delete_attempts = 0
            self.cleared = []

        async def delete_message(self, *, chat_id, message_id):
            self.delete_attempts += 1
            raise RetryAfter("Flood control exceeded. Retry in 9 seconds")

        async def edit_message_reply_markup(self, *, chat_id, message_id, reply_markup=None):
            self.cleared.append((chat_id, message_id, reply_markup))

    old_rid_1 = _insert_reminder_row(
        main_module,
        chat_id=555,
        text="milk",
        created_by=42,
        delivered=1,
        acked=1,
    )
    old_rid_2 = _insert_reminder_row(
        main_module,
        chat_id=555,
        text="milk",
        created_by=42,
        delivered=1,
        acked=1,
    )
    current_rid = _insert_reminder_row(
        main_module,
        chat_id=555,
        text="milk",
        created_by=42,
        delivered=1,
        acked=0,
    )

    main_module.register_reminder_message(old_rid_1, 555, 1001, "delivery")
    main_module.register_reminder_message(old_rid_2, 555, 1002, "delivery")

    bot = BotRetryAfter()

    asyncio.run(
        main_module.delete_old_snoozed_reminder_messages(
            bot,
            current_reminder_id=current_rid,
            chat_id=555,
            text="milk",
            created_by=42,
        )
    )

    assert bot.delete_attempts == 1
    assert bot.cleared == []
    assert [row["message_id"] for row in main_module.get_reminder_messages(old_rid_1)] == [1001]
    assert [row["message_id"] for row in main_module.get_reminder_messages(old_rid_2)] == [1002]
