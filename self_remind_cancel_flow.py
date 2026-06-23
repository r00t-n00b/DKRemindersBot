"""Handle returning from self-remind flow back to choice keyboard."""


async def handle_self_remind_cancel(
    *,
    reminder_id: int,
    query,
    context,
    get_reminder,
    get_source_chat_title_for_self_remind,
    build_self_remind_choice_keyboard,
    msg_source_reminder_not_found: str,
):
    source_reminder = get_reminder(reminder_id)
    if not source_reminder:
        await query.answer(msg_source_reminder_not_found, show_alert=True)
        return

    source_chat_title = await get_source_chat_title_for_self_remind(
        context,
        source_reminder,
        query,
    )

    await query.edit_message_text(
        f'Когда напомнить тебе о "{source_reminder.text}" из чата "{source_chat_title}"?'
    )

    await query.edit_message_reply_markup(
        reply_markup=build_self_remind_choice_keyboard(reminder_id)
    )

    await query.answer("Вернул варианты")
