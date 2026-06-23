"""Handle custom snooze time selection."""

from datetime import datetime


async def handle_custom_snooze_picktime(
    *,
    reminder_id: int,
    date_str: str,
    time_str: str,
    query,
    context,
    tz,
    get_now,
    get_reminder,
    mark_reminder_acked,
    clear_reminder_message_keyboards,
    add_reminder,
    apply_snooze_to_reminder,
    format_snoozed_reminder_text,
    format_snoozed_answer_text,
    msg_reminder_not_found: str,
    msg_reschedule_bad_datetime: str,
    msg_reschedule_past_time: str,
):
    reminder = get_reminder(reminder_id)
    if not reminder:
        await query.answer(msg_reminder_not_found, show_alert=True)
        return

    try:
        year, month, day = map(int, date_str.split("-"))
        hour, minute = map(int, time_str.split(":"))
        new_dt = datetime(year, month, day, hour, minute, tzinfo=tz)
    except Exception:
        await query.answer(msg_reschedule_bad_datetime, show_alert=True)
        return

    if new_dt <= get_now():
        await query.answer(msg_reschedule_past_time, show_alert=True)
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
    )
