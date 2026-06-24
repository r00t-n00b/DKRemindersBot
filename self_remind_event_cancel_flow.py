"""Handle returning from self-remind event-before flow back to event choice keyboard."""

from messages import (
    MSG_RETURNED_EVENT_OPTIONS,
    MSG_RETURNED_OPTIONS,
    MSG_SELF_REMIND_EVENT_DATE_NOT_FOUND_TEXT,
    msg_self_remind_event_before_prompt,
)


async def handle_self_remind_event_cancel(
    *,
    reminder_id: int,
    query,
    get_reminder,
    get_self_remind_event_base,
    extract_event_datetime_from_text,
    build_self_remind_choice_keyboard,
    build_self_remind_event_before_keyboard,
    msg_source_reminder_not_found: str,
):
    source_reminder = get_reminder(reminder_id)
    if not source_reminder:
        await query.answer(msg_source_reminder_not_found, show_alert=True)
        return

    base_now = get_self_remind_event_base(source_reminder)
    event_at = extract_event_datetime_from_text(source_reminder.text, base_now)

    if event_at is None:
        await query.edit_message_text(
            MSG_SELF_REMIND_EVENT_DATE_NOT_FOUND_TEXT,
            reply_markup=build_self_remind_choice_keyboard(reminder_id),
        )
        await query.answer(MSG_RETURNED_OPTIONS)
        return

    event_str = event_at.strftime("%d.%m %H:%M")
    await query.edit_message_text(
        msg_self_remind_event_before_prompt(event_str),
        reply_markup=build_self_remind_event_before_keyboard(reminder_id),
    )
    await query.answer(MSG_RETURNED_EVENT_OPTIONS)
