"""Handle self-remind create flows from callback buttons."""

from dkreminders_bot.ui.messages import MSG_PERSONAL_REMINDER_CREATED, MSG_PICK_DATE, MSG_SELF_REMIND_PRIVATE_START


async def handle_self_remind_event_custom(
    *,
    data: str,
    query,
    get_reminder,
    build_custom_date_keyboard,
    msg_invalid_reminder_id: str,
    msg_source_reminder_not_found: str,
):
    _, _, raw_id = data.split(":", 2)

    try:
        reminder_id = int(raw_id)
    except ValueError:
        await query.answer(msg_invalid_reminder_id, show_alert=True)
        return

    source_reminder = get_reminder(reminder_id)
    if not source_reminder:
        await query.answer(msg_source_reminder_not_found, show_alert=True)
        return

    keyboard = build_custom_date_keyboard(
        reminder_id,
        callback_prefix="selfremind_event",
    )
    await query.edit_message_reply_markup(reply_markup=keyboard)
    await query.answer(MSG_PICK_DATE)


async def handle_self_remind_event_before(
    *,
    data: str,
    query,
    context,
    get_now,
    get_user_chat_id_by_user_id,
    get_reminder,
    get_self_remind_event_base,
    extract_event_datetime_from_text,
    compute_event_before_time,
    get_source_chat_title_for_self_remind,
    normalize_relative_event_date_in_text,
    format_self_remind_text,
    add_reminder,
    format_created_reminder_text,
    build_created_reminder_actions_keyboard_for_reminder,
    msg_invalid_reminder_id: str,
    msg_user_context_missing: str,
    msg_source_reminder_not_found: str,
    msg_event_date_not_found: str,
    msg_unknown_time_option: str,
    msg_reschedule_past_time: str,
):
    _, _, raw_id, option = data.split(":", 3)

    try:
        reminder_id = int(raw_id)
    except ValueError:
        await query.answer(msg_invalid_reminder_id, show_alert=True)
        return

    user_id = getattr(query.from_user, "id", None)
    if user_id is None:
        await query.answer(msg_user_context_missing, show_alert=True)
        return

    target_chat_id = get_user_chat_id_by_user_id(user_id)
    if target_chat_id is None:
        await query.answer(
            MSG_SELF_REMIND_PRIVATE_START,
            show_alert=True,
        )
        return

    source_reminder = get_reminder(reminder_id)
    if not source_reminder:
        await query.answer(msg_source_reminder_not_found, show_alert=True)
        return

    base_now = get_self_remind_event_base(source_reminder)
    event_at = extract_event_datetime_from_text(source_reminder.text, base_now)
    if event_at is None:
        await query.answer(msg_event_date_not_found, show_alert=True)
        return

    remind_at = compute_event_before_time(option, event_at)
    if remind_at is None:
        await query.answer(msg_unknown_time_option, show_alert=True)
        return

    if remind_at <= get_now():
        await query.answer(msg_reschedule_past_time, show_alert=True)
        return

    source_chat_title = await get_source_chat_title_for_self_remind(
        context,
        source_reminder,
        query,
    )
    normalized_src_text = normalize_relative_event_date_in_text(
        source_reminder.text,
        event_at,
    )
    personal_text = format_self_remind_text(source_chat_title, normalized_src_text)

    new_reminder_id = add_reminder(
        chat_id=target_chat_id,
        text=personal_text,
        remind_at=remind_at,
        created_by=user_id,
    )

    when_str = remind_at.strftime("%d.%m %H:%M")
    await query.edit_message_text(
        format_created_reminder_text(when_str, personal_text),
        reply_markup=build_created_reminder_actions_keyboard_for_reminder(new_reminder_id),
    )
    await query.answer(MSG_PERSONAL_REMINDER_CREATED)


async def handle_self_remind_set(
    *,
    data: str,
    query,
    context,
    get_now,
    get_user_chat_id_by_user_id,
    get_reminder,
    compute_self_remind_time,
    get_source_chat_title_for_self_remind,
    format_self_remind_text,
    add_reminder,
    build_custom_date_keyboard,
    format_created_reminder_text,
    build_created_reminder_actions_keyboard_for_reminder,
    msg_invalid_reminder_id: str,
    msg_user_context_missing: str,
    msg_source_reminder_not_found: str,
    get_user_default_time=None,
):
    _, _, raw_id, option = data.split(":", 3)

    try:
        reminder_id = int(raw_id)
    except ValueError:
        await query.answer(msg_invalid_reminder_id, show_alert=True)
        return

    user_id = getattr(query.from_user, "id", None)
    if user_id is None:
        await query.answer(msg_user_context_missing, show_alert=True)
        return

    target_chat_id = get_user_chat_id_by_user_id(user_id)
    if target_chat_id is None:
        await query.answer(
            MSG_SELF_REMIND_PRIVATE_START,
            show_alert=True,
        )
        return

    source_reminder = get_reminder(reminder_id)
    if not source_reminder:
        await query.answer(msg_source_reminder_not_found, show_alert=True)
        return

    if option == "custom":
        keyboard = build_custom_date_keyboard(
            reminder_id,
            callback_prefix="selfremind",
        )
        await query.edit_message_reply_markup(reply_markup=keyboard)
        await query.answer(MSG_PICK_DATE)
        return

    default_time = get_user_default_time(user_id) if get_user_default_time is not None else None
    try:
        remind_at = compute_self_remind_time(
            option,
            get_now(),
            default_time=default_time,
        )
    except TypeError:
        # Backward-compatible for old tests/deps that still provide
        # compute_self_remind_time(option, now).
        remind_at = compute_self_remind_time(option, get_now())

    source_chat_title = await get_source_chat_title_for_self_remind(
        context,
        source_reminder,
        query,
    )
    personal_text = format_self_remind_text(source_chat_title, source_reminder.text)

    new_reminder_id = add_reminder(
        chat_id=target_chat_id,
        text=personal_text,
        remind_at=remind_at,
        created_by=user_id,
        template_id=None,
    )

    when_str = remind_at.strftime("%d.%m %H:%M")
    await query.edit_message_text(
        format_created_reminder_text(when_str, personal_text),
        reply_markup=build_created_reminder_actions_keyboard_for_reminder(new_reminder_id),
    )
    await query.answer(MSG_PERSONAL_REMINDER_CREATED)
