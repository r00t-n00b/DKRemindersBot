"""Handle custom snooze date selection and open time picker."""

from messages import MSG_PICK_TIME


async def enter_custom_snooze_time_picker(
    *,
    reminder_id: int,
    date_str: str,
    query,
    mark_reminder_acked,
    build_custom_time_keyboard,
):
    # выбор даты - реакция
    mark_reminder_acked(reminder_id)

    kb = build_custom_time_keyboard(reminder_id, date_str)
    await query.edit_message_reply_markup(reply_markup=kb)
    await query.answer(MSG_PICK_TIME)
