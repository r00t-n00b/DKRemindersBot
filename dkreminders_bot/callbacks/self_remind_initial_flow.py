"""Handle initial self-remind callback flows."""

from dkreminders_bot.ui.messages import (
    MSG_OK_SHORT,
    MSG_PICK_TIME,
    MSG_RETURNED_CHOICE,
    MSG_SELF_REMIND_CANCELLED,
    MSG_SELF_REMIND_EVENT_DATE_NOT_FOUND_ANSWER,
    MSG_SELF_REMIND_PRIVATE_START,
    MSG_SELF_REMIND_SENT_TO_PRIVATE,
    msg_self_remind_event_before_prompt,
    msg_self_remind_mode_prompt,
    msg_self_remind_regular_prompt,
)


SELF_REMIND_PRIVATE_START_MESSAGE = MSG_SELF_REMIND_PRIVATE_START


async def handle_self_remind_ask(
    *,
    data: str,
    query,
    context,
    parse_required_int_callback_id,
    get_user_chat_id_by_user_id,
    get_reminder,
    get_source_chat_title_for_self_remind,
    build_self_remind_mode_keyboard,
    msg_invalid_reminder_id: str,
    msg_user_context_missing: str,
    msg_source_reminder_not_found: str,
):
    try:
        reminder_id = parse_required_int_callback_id(data, prefix="selfremind:ask:")
    except ValueError:
        await query.answer(msg_invalid_reminder_id, show_alert=True)
        return

    user_id = getattr(query.from_user, "id", None)
    if user_id is None:
        await query.answer(msg_user_context_missing, show_alert=True)
        return

    target_chat_id = get_user_chat_id_by_user_id(user_id)
    if target_chat_id is None:
        await query.answer(SELF_REMIND_PRIVATE_START_MESSAGE, show_alert=True)
        return

    source_reminder = get_reminder(reminder_id)
    if not source_reminder:
        await query.answer(msg_source_reminder_not_found, show_alert=True)
        return

    source_chat_title = await get_source_chat_title_for_self_remind(
        context,
        source_reminder,
        query,
    )

    await context.bot.send_message(
        chat_id=target_chat_id,
        text=msg_self_remind_mode_prompt(source_reminder.text, source_chat_title),
        reply_markup=build_self_remind_mode_keyboard(reminder_id),
    )
    await query.answer(MSG_SELF_REMIND_SENT_TO_PRIVATE)


async def handle_self_remind_cancel_personal(
    *,
    data: str,
    query,
    parse_required_int_callback_id,
    msg_invalid_reminder_id: str,
):
    try:
        parse_required_int_callback_id(data, prefix="selfremind:cancel_personal:")
    except ValueError:
        await query.answer(msg_invalid_reminder_id, show_alert=True)
        return

    if query.message:
        await query.edit_message_text(MSG_SELF_REMIND_CANCELLED)

    await query.answer(MSG_OK_SHORT)


async def handle_self_remind_back(
    *,
    data: str,
    query,
    context,
    parse_required_int_callback_id,
    get_reminder,
    get_source_chat_title_for_self_remind,
    build_self_remind_mode_keyboard,
    msg_invalid_reminder_id: str,
    msg_source_reminder_not_found: str,
):
    try:
        reminder_id = parse_required_int_callback_id(data, prefix="selfremind:back:")
    except ValueError:
        await query.answer(msg_invalid_reminder_id, show_alert=True)
        return

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
        msg_self_remind_mode_prompt(source_reminder.text, source_chat_title),
        reply_markup=build_self_remind_mode_keyboard(reminder_id),
    )
    await query.answer(MSG_RETURNED_CHOICE)


async def handle_self_remind_mode(
    *,
    data: str,
    query,
    context,
    parse_required_int_callback_id,
    get_user_chat_id_by_user_id,
    get_reminder,
    get_source_chat_title_for_self_remind,
    get_self_remind_event_base,
    extract_event_datetime_from_text,
    build_self_remind_choice_keyboard,
    build_self_remind_event_before_keyboard,
    msg_invalid_reminder_id: str,
    msg_user_context_missing: str,
    msg_source_reminder_not_found: str,
    msg_event_date_not_found: str,
    msg_unknown_self_remind_mode: str,
):
    raw_payload = data[len("selfremind:mode:"):]
    raw_id, mode = raw_payload.split(":", 1)

    try:
        reminder_id = parse_required_int_callback_id(
            f"selfremind:mode:{raw_id}",
            prefix="selfremind:mode:",
        )
    except ValueError:
        await query.answer(msg_invalid_reminder_id, show_alert=True)
        return

    user_id = getattr(query.from_user, "id", None)
    if user_id is None:
        await query.answer(msg_user_context_missing, show_alert=True)
        return

    target_chat_id = get_user_chat_id_by_user_id(user_id)
    if target_chat_id is None:
        await query.answer(SELF_REMIND_PRIVATE_START_MESSAGE, show_alert=True)
        return

    source_reminder = get_reminder(reminder_id)
    if not source_reminder:
        await query.answer(msg_source_reminder_not_found, show_alert=True)
        return

    if mode == "regular":
        source_chat_title = await get_source_chat_title_for_self_remind(
            context,
            source_reminder,
            query,
        )
        await query.edit_message_text(
            msg_self_remind_regular_prompt(source_reminder.text, source_chat_title),
            reply_markup=build_self_remind_choice_keyboard(reminder_id),
        )
        await query.answer(MSG_PICK_TIME)
        return

    if mode == "event":
        base_now = get_self_remind_event_base(source_reminder)
        event_at = extract_event_datetime_from_text(source_reminder.text, base_now)

        if event_at is None:
            await query.edit_message_text(
                msg_event_date_not_found,
                reply_markup=build_self_remind_choice_keyboard(reminder_id),
            )
            await query.answer(MSG_SELF_REMIND_EVENT_DATE_NOT_FOUND_ANSWER)
            return

        event_str = event_at.strftime("%d.%m %H:%M")
        await query.edit_message_text(
            msg_self_remind_event_before_prompt(event_str),
            reply_markup=build_self_remind_event_before_keyboard(reminder_id),
        )
        await query.answer(MSG_PICK_TIME)
        return

    await query.answer(msg_unknown_self_remind_mode, show_alert=True)
