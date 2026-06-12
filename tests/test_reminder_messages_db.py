def test_register_and_get_reminder_messages(main_module):
    reminder_id = main_module.add_reminder(
        chat_id=456,
        text="message tracking test",
        remind_at=main_module.get_now(),
        created_by=123,
    )

    main_module.register_reminder_message(
        reminder_id=reminder_id,
        chat_id=456,
        message_id=1001,
        kind="delivery",
    )
    main_module.register_reminder_message(
        reminder_id=reminder_id,
        chat_id=456,
        message_id=1002,
        kind="nudge",
    )

    rows = main_module.get_reminder_messages(reminder_id)

    assert [
        {
            "reminder_id": row["reminder_id"],
            "chat_id": row["chat_id"],
            "message_id": row["message_id"],
            "kind": row["kind"],
        }
        for row in rows
    ] == [
        {
            "reminder_id": reminder_id,
            "chat_id": 456,
            "message_id": 1001,
            "kind": "delivery",
        },
        {
            "reminder_id": reminder_id,
            "chat_id": 456,
            "message_id": 1002,
            "kind": "nudge",
        },
    ]


def test_register_reminder_message_is_idempotent(main_module):
    reminder_id = main_module.add_reminder(
        chat_id=456,
        text="message tracking idempotent test",
        remind_at=main_module.get_now(),
        created_by=123,
    )

    main_module.register_reminder_message(
        reminder_id=reminder_id,
        chat_id=456,
        message_id=1001,
        kind="delivery",
    )
    main_module.register_reminder_message(
        reminder_id=reminder_id,
        chat_id=456,
        message_id=1001,
        kind="delivery",
    )

    rows = main_module.get_reminder_messages(reminder_id)

    assert len(rows) == 1
    assert rows[0]["message_id"] == 1001
    assert rows[0]["kind"] == "delivery"


def test_get_reminder_messages_for_unknown_reminder_returns_empty_list(main_module):
    assert main_module.get_reminder_messages(999999) == []
