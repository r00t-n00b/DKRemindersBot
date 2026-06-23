"""Handle entering custom snooze date picker."""


async def enter_custom_snooze_flow(
    *,
    reminder_id: int,
    query,
    mark_reminder_acked,
    build_custom_date_keyboard,
):
    mark_reminder_acked(reminder_id)

    kb = build_custom_date_keyboard(reminder_id)
    await query.edit_message_reply_markup(reply_markup=kb)
    await query.answer("Выбери дату", show_alert=False)
