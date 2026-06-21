import messages


def test_messages_catalog_exports_known_user_facing_messages(main_module):
    expected = {
        "MSG_REMIND_USAGE",
        "MSG_NOT_UNDERSTOOD_PLAIN_TEXT",
        "MSG_GROUP_USERNAME_PREFIX_FORBIDDEN",
        "MSG_GROUP_ALIAS_PREFIX_FORBIDDEN",
        "MSG_INVALID_REMINDER_ID",
        "MSG_REMINDER_NOT_FOUND",
        "MSG_SOURCE_REMINDER_NOT_FOUND",
        "MSG_REMINDER_ALREADY_DELETED_ALERT",
        "MSG_REMINDER_ALREADY_DELETED_TEXT",
        "MSG_DELETE_FAILED_SHORT",
        "MSG_DELETE_FAILED_TEXT",
        "MSG_RESCHEDULE_OPEN_FAILED_TEXT",
        "MSG_PARSE_DATE_TEXT_FAILED",
        "MSG_UNEXPECTED_CALLBACK_ERROR",
        "MSG_DELETE_SERIES_FAILED",
        "MSG_UNDO_EXPIRED",
        "MSG_UNDO_RESTORE_FAILED",
        "MSG_USER_CONTEXT_MISSING",
        "MSG_EVENT_DATE_NOT_FOUND",
        "MSG_UNKNOWN_SELF_REMIND_MODE",
        "MSG_UNKNOWN_TIME_OPTION",
        "MSG_RESCHEDULE_UNKNOWN_ACTION",
        "MSG_RESCHEDULE_BAD_DATETIME",
        "MSG_RESCHEDULE_PAST_TIME",
        "msg_recurring_missing_dash",
        "msg_recurring_parse_failed",
        "msg_after_me_requires_date_and_text",
        "msg_user_has_not_started_bot",
        "msg_after_target_requires_date_and_text",
    }

    assert expected <= set(messages.__all__)

    for name in expected:
        assert getattr(main_module, name) is getattr(messages, name)


def test_messages_catalog_keeps_error_texts_human_readable():
    suspicious_fragments = [
        "Произошла ошибка",
        "Некорректный reminder id",
        "Traceback",
    ]

    for name in messages.__all__:
        value = getattr(messages, name)
        if callable(value):
            continue

        for fragment in suspicious_fragments:
            assert fragment not in value, name
