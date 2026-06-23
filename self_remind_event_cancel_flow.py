"""Handle returning from self-remind event-before flow back to event choice keyboard."""


async def handle_self_remind_event_cancel(
    *,
    reminder_id: int,
    query,
    get_reminder,
    get_self_remind_event_base,
    extract_event_datetime_from_text,
    build_self_remind_choice_keyboard,
    build_self_remind_event_before_keyboard,
    msg_source_reminder_not_found: str,
):
    source_reminder = get_reminder(reminder_id)
    if not source_reminder:
        await query.answer(msg_source_reminder_not_found, show_alert=True)
        return

    base_now = get_self_remind_event_base(source_reminder)
    event_at = extract_event_datetime_from_text(source_reminder.text, base_now)

    if event_at is None:
        await query.edit_message_text(
            "Я не смог понять дату события из текста.\n"
            "Ты можешь поставить себе обычный ремайндер:",
            reply_markup=build_self_remind_choice_keyboard(reminder_id),
        )
        await query.answer("Вернул варианты")
        return

    event_str = event_at.strftime("%d.%m %H:%M")
    await query.edit_message_text(
        f"Я понял, что событие из напоминания состоится {event_str}.\n"
        "За сколько до этого времени напомнить?",
        reply_markup=build_self_remind_event_before_keyboard(reminder_id),
    )
    await query.answer("Вернул варианты до события")
