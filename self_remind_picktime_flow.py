"""Handle self-remind custom time selection and create the personal reminder."""

from messages import MSG_PERSONAL_REMINDER_CREATED, MSG_SELF_REMIND_PRIVATE_START

from datetime import datetime

from self_remind_calendar_flow import get_self_remind_callback_prefix


async def handle_self_remind_picktime(
    *,
    data: str,
    query,
    context,
    tz,
    get_now,
    get_user_chat_id_by_user_id,
    get_reminder,
    get_source_chat_title_for_self_remind,
    add_reminder,
    build_created_reminder_actions_keyboard_for_reminder,
    format_self_remind_text,
    format_created_reminder_text,
    msg_user_context_missing: str,
    msg_source_reminder_not_found: str,
    msg_reschedule_bad_datetime: str,
    msg_reschedule_past_time: str,
):
    callback_prefix = get_self_remind_callback_prefix(data)
    raw_prefix = f"{callback_prefix}_picktime:"

    raw_payload = data[len(raw_prefix):]
    raw_id, date_str, time_str = raw_payload.split(":", 2)
    reminder_id = int(raw_id)

    user_id = getattr(query.from_user, "id", None)
    if user_id is None:
        await query.answer(msg_user_context_missing, show_alert=True)
        return

    target_chat_id = get_user_chat_id_by_user_id(user_id)
    if target_chat_id is None:
        await query.answer(
            MSG_SELF_REMIND_PRIVATE_START,
            show_alert=True,
        )
        return

    source_reminder = get_reminder(reminder_id)
    if not source_reminder:
        await query.answer(msg_source_reminder_not_found, show_alert=True)
        return

    try:
        year, month, day = map(int, date_str.split("-"))
        hour, minute = map(int, time_str.split(":"))
        remind_at = datetime(year, month, day, hour, minute, tzinfo=tz)
    except Exception:
        await query.answer(msg_reschedule_bad_datetime, show_alert=True)
        return

    if remind_at <= get_now():
        await query.answer(msg_reschedule_past_time, show_alert=True)
        return

    source_chat_title = await get_source_chat_title_for_self_remind(
        context,
        source_reminder,
        query,
    )
    personal_text = format_self_remind_text(source_chat_title, source_reminder.text)

    new_reminder_id = add_reminder(
        chat_id=target_chat_id,
        text=personal_text,
        remind_at=remind_at,
        created_by=user_id,
        template_id=None,
    )

    when_str = remind_at.strftime("%d.%m %H:%M")
    await query.edit_message_text(
        format_created_reminder_text(when_str, personal_text),
        reply_markup=build_created_reminder_actions_keyboard_for_reminder(new_reminder_id),
    )
    await query.answer(MSG_PERSONAL_REMINDER_CREATED)
