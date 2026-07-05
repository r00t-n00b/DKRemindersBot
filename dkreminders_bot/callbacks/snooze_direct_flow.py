"""Handle direct snooze actions like +20m, +1h, custom."""


async def handle_direct_snooze_action(
    *,
    reminder_id: int,
    action: str,
    query,
    context,
    get_now,
    get_user_default_time,
    get_reminder,
    compute_snooze_target_time,
    enter_custom_snooze_flow,
    apply_snooze_to_reminder,
    mark_reminder_acked,
    clear_reminder_message_keyboards,
    add_reminder,
    build_custom_date_keyboard,
    format_snoozed_reminder_text,
    format_snoozed_answer_text,
    delete_old_snoozed_reminder_messages=None,
    delete_other_reminder_messages=None,
    msg_reminder_not_found: str = "",
    msg_reschedule_unknown_action: str,
):
    reminder = get_reminder(reminder_id)
    if not reminder:
        await query.answer(msg_reminder_not_found, show_alert=True)
        return

    if action == "custom":
        await enter_custom_snooze_flow(
            reminder_id=reminder_id,
            query=query,
            mark_reminder_acked=mark_reminder_acked,
            build_custom_date_keyboard=build_custom_date_keyboard,
            context=context,
            clear_reminder_message_keyboards=clear_reminder_message_keyboards,
            delete_other_reminder_messages=delete_other_reminder_messages,
        )
        return

    try:
        new_dt = compute_snooze_target_time(
            action,
            get_now(),
            default_time=get_user_default_time(
                getattr(getattr(query, "from_user", None), "id", None)
            ),
        )
    except ValueError:
        await query.answer(msg_reschedule_unknown_action, show_alert=True)
        return

    await apply_snooze_to_reminder(
        reminder=reminder,
        new_dt=new_dt,
        query=query,
        context=context,
        mark_reminder_acked=mark_reminder_acked,
        clear_reminder_message_keyboards=clear_reminder_message_keyboards,
        add_reminder=add_reminder,
        format_snoozed_reminder_text=format_snoozed_reminder_text,
        format_snoozed_answer_text=format_snoozed_answer_text,
        delete_old_snoozed_reminder_messages=delete_old_snoozed_reminder_messages,
        delete_other_reminder_messages=delete_other_reminder_messages,
    )
