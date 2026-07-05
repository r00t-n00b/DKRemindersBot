"""Handle custom snooze cancellation and return to snooze options."""

from messages import MSG_RETURNED_OPTIONS


async def handle_custom_snooze_cancel(
    *,
    reminder_id,
    query,
    mark_reminder_acked,
    build_snooze_keyboard,
    msg_invalid_reminder_id: str,
    get_reminder=None,
):
    if reminder_id is not None:
        reminder = get_reminder(reminder_id) if callable(get_reminder) else None
        if reminder is not None and (
            int(getattr(reminder, "acked", 0) or 0)
            or int(getattr(reminder, "delivered", 0) or 0)
        ):
            await query.edit_message_reply_markup(reply_markup=None)
            await query.answer("Это напоминание уже обработано", show_alert=True)
            return

        mark_reminder_acked(reminder_id)

        await query.edit_message_reply_markup(
            reply_markup=build_snooze_keyboard(reminder_id),
        )
        await query.answer(MSG_RETURNED_OPTIONS)
        return

    await query.answer(msg_invalid_reminder_id, show_alert=True)
