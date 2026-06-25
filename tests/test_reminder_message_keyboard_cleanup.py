import asyncio


class FakeBot:
    def __init__(self):
        self.markup_edits = []
        self.text_edits = []

    async def edit_message_reply_markup(self, **kwargs):
        self.markup_edits.append(kwargs)

    async def edit_message_text(self, **kwargs):
        self.text_edits.append(kwargs)


class PartiallyFailingBot:
    def __init__(self):
        self.markup_edits = []
        self.text_edits = []

    async def edit_message_reply_markup(self, **kwargs):
        self.markup_edits.append(kwargs)
        if kwargs["message_id"] == 1001:
            raise RuntimeError("telegram markup edit failed")

    async def edit_message_text(self, **kwargs):
        self.text_edits.append(kwargs)
        if kwargs["message_id"] == 1001:
            raise RuntimeError("telegram text edit failed")


def test_clear_reminder_message_keyboards_clears_all_registered_messages(main_module):
    reminder_id = main_module.add_reminder(
        chat_id=456,
        text="cleanup test",
        remind_at=main_module.get_now(),
        created_by=123,
    )

    main_module.register_reminder_message(reminder_id, 456, 1001, "delivery")
    main_module.register_reminder_message(reminder_id, 456, 1002, "nudge")

    bot = FakeBot()

    asyncio.run(main_module.clear_reminder_message_keyboards(bot, reminder_id))

    assert bot.markup_edits == [
        {
            "chat_id": 456,
            "message_id": 1001,
            "reply_markup": None,
        },
        {
            "chat_id": 456,
            "message_id": 1002,
            "reply_markup": None,
        },
    ]
    assert bot.text_edits == []


def test_clear_reminder_message_keyboards_replaces_text_for_all_registered_messages(main_module):
    reminder_id = main_module.add_reminder(
        chat_id=456,
        text="cleanup replace text test",
        remind_at=main_module.get_now(),
        created_by=123,
    )

    main_module.register_reminder_message(reminder_id, 456, 1001, "delivery")
    main_module.register_reminder_message(reminder_id, 456, 1002, "nudge")

    bot = FakeBot()

    asyncio.run(
        main_module.clear_reminder_message_keyboards(
            bot,
            reminder_id,
            replacement_text="Напоминание отложено до 25.06 16:00",
        )
    )

    assert bot.text_edits == [
        {
            "chat_id": 456,
            "message_id": 1001,
            "text": "Напоминание отложено до 25.06 16:00",
            "reply_markup": None,
        },
        {
            "chat_id": 456,
            "message_id": 1002,
            "text": "Напоминание отложено до 25.06 16:00",
            "reply_markup": None,
        },
    ]
    assert bot.markup_edits == []


def test_clear_reminder_message_keyboards_falls_back_to_markup_after_text_edit_failure(main_module):
    reminder_id = main_module.add_reminder(
        chat_id=456,
        text="cleanup replacement failure test",
        remind_at=main_module.get_now(),
        created_by=123,
    )

    main_module.register_reminder_message(reminder_id, 456, 1001, "delivery")
    main_module.register_reminder_message(reminder_id, 456, 1002, "nudge")

    bot = PartiallyFailingBot()

    asyncio.run(
        main_module.clear_reminder_message_keyboards(
            bot,
            reminder_id,
            replacement_text="Обновленный текст",
        )
    )

    assert bot.text_edits == [
        {
            "chat_id": 456,
            "message_id": 1001,
            "text": "Обновленный текст",
            "reply_markup": None,
        },
        {
            "chat_id": 456,
            "message_id": 1002,
            "text": "Обновленный текст",
            "reply_markup": None,
        },
    ]
    assert bot.markup_edits == [
        {
            "chat_id": 456,
            "message_id": 1001,
            "reply_markup": None,
        },
    ]


def test_clear_reminder_message_keyboards_continues_after_edit_failure(main_module):
    reminder_id = main_module.add_reminder(
        chat_id=456,
        text="cleanup failure test",
        remind_at=main_module.get_now(),
        created_by=123,
    )

    main_module.register_reminder_message(reminder_id, 456, 1001, "delivery")
    main_module.register_reminder_message(reminder_id, 456, 1002, "nudge")

    bot = PartiallyFailingBot()

    asyncio.run(main_module.clear_reminder_message_keyboards(bot, reminder_id))

    assert bot.markup_edits == [
        {
            "chat_id": 456,
            "message_id": 1001,
            "reply_markup": None,
        },
        {
            "chat_id": 456,
            "message_id": 1002,
            "reply_markup": None,
        },
    ]
    assert bot.text_edits == []


def test_clear_reminder_message_keyboards_no_registered_messages_is_noop(main_module):
    bot = FakeBot()

    asyncio.run(main_module.clear_reminder_message_keyboards(bot, 999999))

    assert bot.markup_edits == []
    assert bot.text_edits == []
