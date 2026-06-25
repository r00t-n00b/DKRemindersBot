"""Handle entering custom snooze date picker."""

from messages import MSG_PICK_DATE


async def enter_custom_snooze_flow(
    *,
    reminder_id: int,
    query,
    mark_reminder_acked,
    build_custom_date_keyboard,
    context=None,
    clear_reminder_message_keyboards=None,
):
    mark_reminder_acked(reminder_id)

    if context is not None and clear_reminder_message_keyboards is not None:
        await clear_reminder_message_keyboards(context.bot, reminder_id)

    kb = build_custom_date_keyboard(reminder_id)
    await query.edit_message_reply_markup(reply_markup=kb)
    await query.answer(MSG_PICK_DATE, show_alert=False)
