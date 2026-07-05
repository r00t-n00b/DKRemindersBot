"""Small callback flows used by the main callback router."""

from dkreminders_bot.ui.messages import MSG_PAST_DATE_ALERT

async def handle_pastdate_callback(*, query):
    await query.answer(MSG_PAST_DATE_ALERT, show_alert=True)


async def handle_noop_callback(*, query):
    await query.answer()


async def handle_self_remind_event_cancel_callback(
    *,
    data: str,
    query,
    parse_required_int_callback_id,
    handle_self_remind_event_cancel,
    get_reminder,
    get_self_remind_event_base,
    extract_event_datetime_from_text,
    build_self_remind_choice_keyboard,
    build_self_remind_event_before_keyboard,
    msg_invalid_reminder_id: str,
    msg_source_reminder_not_found: str,
):
    try:
        reminder_id = parse_required_int_callback_id(
            data,
            prefix="selfremind_event_cancel:",
        )
    except ValueError:
        await query.answer(msg_invalid_reminder_id, show_alert=True)
        return

    await handle_self_remind_event_cancel(
        reminder_id=reminder_id,
        query=query,
        get_reminder=get_reminder,
        get_self_remind_event_base=get_self_remind_event_base,
        extract_event_datetime_from_text=extract_event_datetime_from_text,
        build_self_remind_choice_keyboard=build_self_remind_choice_keyboard,
        build_self_remind_event_before_keyboard=build_self_remind_event_before_keyboard,
        msg_source_reminder_not_found=msg_source_reminder_not_found,
    )


async def handle_self_remind_cancel_callback(
    *,
    data: str,
    query,
    context,
    parse_required_int_callback_id,
    handle_self_remind_cancel,
    get_reminder,
    get_source_chat_title_for_self_remind,
    build_self_remind_choice_keyboard,
    msg_invalid_reminder_id: str,
    msg_source_reminder_not_found: str,
):
    try:
        reminder_id = parse_required_int_callback_id(
            data,
            prefix="selfremind_cancel:",
        )
    except ValueError:
        await query.answer(msg_invalid_reminder_id, show_alert=True)
        return

    await handle_self_remind_cancel(
        reminder_id=reminder_id,
        query=query,
        context=context,
        get_reminder=get_reminder,
        get_source_chat_title_for_self_remind=get_source_chat_title_for_self_remind,
        build_self_remind_choice_keyboard=build_self_remind_choice_keyboard,
        msg_source_reminder_not_found=msg_source_reminder_not_found,
    )


async def handle_done_callback_data(
    *,
    data: str,
    query,
    context,
    parse_optional_int_callback_id,
    handle_done_callback,
    mark_reminder_acked,
    clear_reminder_message_keyboards,
    get_reminder,
    format_completed_reminder_text,
    delete_old_snoozed_reminder_messages=None,
    delete_other_reminder_messages=None,
):
    reminder_id = parse_optional_int_callback_id(data, prefix="done:")

    await handle_done_callback(
        reminder_id=reminder_id,
        query=query,
        context=context,
        mark_reminder_acked=mark_reminder_acked,
        clear_reminder_message_keyboards=clear_reminder_message_keyboards,
        get_reminder=get_reminder,
        format_completed_reminder_text=format_completed_reminder_text,
        delete_old_snoozed_reminder_messages=delete_old_snoozed_reminder_messages,
        delete_other_reminder_messages=delete_other_reminder_messages,
    )


async def handle_snooze_current_month_callback(
    *,
    data: str,
    query,
    get_today,
    parse_required_int_callback_id,
    show_custom_snooze_calendar,
    build_custom_date_keyboard,
):
    reminder_id = parse_required_int_callback_id(
        data,
        prefix="snooze_caltoday:",
    )

    today = get_today()
    await show_custom_snooze_calendar(
        reminder_id=reminder_id,
        query=query,
        year=today.year,
        month=today.month,
        build_custom_date_keyboard=build_custom_date_keyboard,
        ignore_edit_errors=True,
    )


async def handle_snooze_cancel_callback_data(
    *,
    data: str,
    query,
    parse_optional_int_callback_id,
    handle_custom_snooze_cancel,
    mark_reminder_acked,
    build_snooze_keyboard,
    msg_invalid_reminder_id: str,
    get_reminder=None,
):
    reminder_id = parse_optional_int_callback_id(data, prefix="snooze_cancel:")

    await handle_custom_snooze_cancel(
        reminder_id=reminder_id,
        query=query,
        mark_reminder_acked=mark_reminder_acked,
        build_snooze_keyboard=build_snooze_keyboard,
        msg_invalid_reminder_id=msg_invalid_reminder_id,
        get_reminder=get_reminder,
    )
