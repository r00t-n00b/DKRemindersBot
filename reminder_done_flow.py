"""Handle marking reminder message as completed from callback."""


async def handle_done_callback(
    *,
    reminder_id,
    query,
    context,
    mark_reminder_acked,
    clear_reminder_message_keyboards,
    get_reminder,
    format_completed_reminder_text,
):
    if reminder_id is not None:
        mark_reminder_acked(reminder_id)
        await clear_reminder_message_keyboards(context.bot, reminder_id)

    original_text = query.message.text if query.message and query.message.text else ""

    if reminder_id is not None:
        reminder = get_reminder(reminder_id)
    else:
        reminder = None

    base_text = reminder.text if reminder else original_text or "Напоминание"
    new_text = format_completed_reminder_text(base_text)

    if hasattr(query, "edit_message_text"):
        try:
            await query.edit_message_text(new_text)
        except Exception:
            pass

    if hasattr(query, "edit_message_reply_markup"):
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

    await query.answer("Отмечено как завершенное")
