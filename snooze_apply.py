"""Apply a successful snooze action."""


async def apply_snooze_to_reminder(
    *,
    reminder,
    new_dt,
    query,
    context,
    mark_reminder_acked,
    clear_reminder_message_keyboards,
    add_reminder,
    format_snoozed_reminder_text,
    format_snoozed_answer_text,
):
    # УСПЕШНЫЙ snooze = реакция пользователя
    mark_reminder_acked(reminder.id)
    await clear_reminder_message_keyboards(context.bot, reminder.id)

    add_reminder(
        chat_id=reminder.chat_id,
        text=reminder.text,
        remind_at=new_dt,
        created_by=reminder.created_by,
        template_id=None,
    )
    when_str = new_dt.strftime("%d.%m %H:%M")

    try:
        await query.edit_message_text(format_snoozed_reminder_text(reminder.text, when_str))
    except Exception:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

    await query.answer(format_snoozed_answer_text(when_str))
