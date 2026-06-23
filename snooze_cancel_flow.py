"""Handle custom snooze cancellation and return to snooze options."""


async def handle_custom_snooze_cancel(
    *,
    reminder_id,
    query,
    mark_reminder_acked,
    build_snooze_keyboard,
    msg_invalid_reminder_id: str,
):
    if reminder_id is not None:
        mark_reminder_acked(reminder_id)

        await query.edit_message_reply_markup(
            reply_markup=build_snooze_keyboard(reminder_id),
        )
        await query.answer("Вернул варианты")
        return

    await query.answer(msg_invalid_reminder_id, show_alert=True)
