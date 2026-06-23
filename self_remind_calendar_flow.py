"""Handle self-remind custom calendar navigation and date selection."""


def get_self_remind_callback_prefix(data: str) -> str:
    return "selfremind_event" if data.startswith("selfremind_event_") else "selfremind"


async def handle_self_remind_calendar_today(
    *,
    data: str,
    query,
    get_today,
    parse_required_int_callback_id,
    build_custom_date_keyboard,
):
    callback_prefix = get_self_remind_callback_prefix(data)
    reminder_id = parse_required_int_callback_id(
        data,
        prefix=f"{callback_prefix}_caltoday:",
    )

    today = get_today()
    keyboard = build_custom_date_keyboard(
        reminder_id,
        year=today.year,
        month=today.month,
        callback_prefix=callback_prefix,
    )

    try:
        await query.edit_message_reply_markup(reply_markup=keyboard)
    except Exception:
        pass

    await query.answer()


async def handle_self_remind_pickdate(
    *,
    data: str,
    query,
    parse_required_int_callback_id,
    build_custom_time_keyboard,
):
    callback_prefix = get_self_remind_callback_prefix(data)
    raw_prefix = f"{callback_prefix}_pickdate:"

    raw_payload = data[len(raw_prefix):]
    raw_id, date_str = raw_payload.split(":", 1)
    reminder_id = int(raw_id)

    # Keep the parser dependency explicit so the id parsing contract stays shared.
    parsed_id = parse_required_int_callback_id(
        f"{raw_prefix}{raw_id}",
        prefix=raw_prefix,
    )
    if parsed_id != reminder_id:
        raise ValueError("parsed reminder id mismatch")

    keyboard = build_custom_time_keyboard(
        reminder_id,
        date_str,
        callback_prefix=callback_prefix,
    )
    await query.edit_message_reply_markup(reply_markup=keyboard)
    await query.answer("Выбери время")
