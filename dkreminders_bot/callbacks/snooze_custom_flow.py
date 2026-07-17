"""Handle entering custom snooze date picker."""

from dkreminders_bot.ui.messages import MSG_PICK_DATE


async def enter_custom_snooze_flow(
    *,
    reminder_id: int,
    query,
    mark_reminder_acked,
    build_custom_date_keyboard,
    context=None,
    clear_reminder_message_keyboards=None,
    delete_other_reminder_messages=None,
):
    # Opening the custom picker is only navigation, not handling the reminder.
    # Keep the reminder unacked so Cancel can return to the original options.
    clicked_message = getattr(query, "message", None)
    clicked_chat_id = getattr(clicked_message, "chat_id", None)
    clicked_message_id = getattr(clicked_message, "message_id", None)

    if (
        context is not None
        and delete_other_reminder_messages is not None
        and clicked_chat_id is not None
        and clicked_message_id is not None
    ):
        await delete_other_reminder_messages(
            context.bot,
            reminder_id=reminder_id,
            keep_chat_id=clicked_chat_id,
            keep_message_id=clicked_message_id,
        )
    elif context is not None and clear_reminder_message_keyboards is not None:
        await clear_reminder_message_keyboards(context.bot, reminder_id)

    kb = build_custom_date_keyboard(reminder_id)
    await query.edit_message_reply_markup(reply_markup=kb)
    await query.answer(MSG_PICK_DATE, show_alert=False)
