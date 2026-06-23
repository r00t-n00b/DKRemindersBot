"""Handle custom snooze calendar navigation."""


async def show_custom_snooze_calendar(
    *,
    reminder_id: int,
    query,
    year: int,
    month: int,
    build_custom_date_keyboard,
    ignore_edit_errors: bool = False,
):
    kb = build_custom_date_keyboard(reminder_id, year=year, month=month)

    if ignore_edit_errors:
        try:
            await query.edit_message_reply_markup(reply_markup=kb)
        except Exception:
            pass
    else:
        await query.edit_message_reply_markup(reply_markup=kb)

    await query.answer()
