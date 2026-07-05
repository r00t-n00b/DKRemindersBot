"""Handle marking reminder message as completed from callback."""

from messages import MSG_DONE_COMPLETED


async def handle_done_callback(
    *,
    reminder_id,
    query,
    context,
    mark_reminder_acked,
    clear_reminder_message_keyboards,
    get_reminder,
    format_completed_reminder_text,
    delete_old_snoozed_reminder_messages=None,
    delete_other_reminder_messages=None,
):
    original_text = query.message.text if query.message and query.message.text else ""

    if reminder_id is not None:
        reminder = get_reminder(reminder_id)
    else:
        reminder = None

    base_text = reminder.text if reminder else original_text or "Напоминание"
    new_text = format_completed_reminder_text(base_text)

    if reminder_id is not None:
        bot = getattr(context, "bot", None)
        if reminder is not None and bot is not None and delete_old_snoozed_reminder_messages is not None:
            await delete_old_snoozed_reminder_messages(
                bot,
                current_reminder_id=reminder.id,
                chat_id=reminder.chat_id,
                text=reminder.text,
                created_by=reminder.created_by,
            )

        mark_reminder_acked(reminder_id)
        bot = getattr(context, "bot", None)
        clicked_message = getattr(query, "message", None)
        clicked_chat_id = getattr(clicked_message, "chat_id", None)
        clicked_message_id = getattr(clicked_message, "message_id", None)

        if (
            bot is not None
            and delete_other_reminder_messages is not None
            and clicked_chat_id is not None
            and clicked_message_id is not None
        ):
            await delete_other_reminder_messages(
                bot,
                reminder_id=reminder_id,
                keep_chat_id=clicked_chat_id,
                keep_message_id=clicked_message_id,
            )
        elif bot is not None:
            await clear_reminder_message_keyboards(
                bot,
                reminder_id,
                replacement_text=new_text,
            )

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

    await query.answer(MSG_DONE_COMPLETED)
