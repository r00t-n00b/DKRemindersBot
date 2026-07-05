"""Handle one-line recurring /remind flow."""

from timezone_features import timezone_label


def _sent_chat_id(sent_message, fallback_message):
    chat_id = getattr(sent_message, "chat_id", None)
    if chat_id is not None:
        return chat_id
    chat = getattr(sent_message, "chat", None)
    chat_id = getattr(chat, "id", None)
    if chat_id is not None:
        return chat_id
    chat = getattr(fallback_message, "chat", None)
    return getattr(chat, "id", None)


def _register_created_message(register_reminder_message, *, reminder_id, sent_message, fallback_message):
    if not callable(register_reminder_message) or sent_message is None:
        return

    message_id = getattr(sent_message, "message_id", None)
    chat_id = _sent_chat_id(sent_message, fallback_message)
    if message_id is None or chat_id is None:
        return

    register_reminder_message(
        reminder_id=reminder_id,
        chat_id=chat_id,
        message_id=message_id,
        kind="created",
    )


async def try_handle_single_recurring_reminder(
    *,
    raw_single: str,
    now,
    target_chat_id: int,
    used_alias,
    chat,
    user,
    message,
    is_private: bool,
    default_time,
    looks_like_recurring,
    parse_with_optional_default_time,
    parse_recurring,
    create_recurring_template,
    add_reminder,
    build_created_reminder_actions_keyboard,
    format_recurring_human,
    format_created_recurring_reminder_text,
    msg_recurring_parse_failed,
    safe_reply,
    logger,
    register_reminder_message=None,
) -> bool:
    if not looks_like_recurring(raw_single):
        return False

    try:
        first_dt, text, pattern_type, payload, hour, minute = parse_with_optional_default_time(
            parse_recurring,
            raw_single,
            now,
            default_time=default_time,
        )
    except ValueError as e:
        logger.info(
            "REMIND recurring parse failed user=%s chat=%s raw=%r error=%s",
            user.id,
            chat.id,
            raw_single,
            e,
        )
        await safe_reply(message, msg_recurring_parse_failed(is_private))
        return True

    tpl_id = create_recurring_template(
        chat_id=target_chat_id,
        text=text,
        pattern_type=pattern_type,
        payload=payload,
        time_hour=hour,
        time_minute=minute,
        created_by=user.id,
    )
    reminder_id = add_reminder(
        chat_id=target_chat_id,
        text=text,
        remind_at=first_dt,
        created_by=user.id,
        template_id=tpl_id,
    )

    logger.info(
        "Создан recurring reminder id=%s tpl_id=%s chat_id=%s at=%s text=%s (from chat %s, user %s)",
        reminder_id,
        tpl_id,
        target_chat_id,
        first_dt.isoformat(),
        text,
        chat.id,
        user.id,
    )

    display_tz = getattr(now, "tzinfo", None)
    display_tz_name = getattr(display_tz, "key", None)
    display_dt = first_dt.astimezone(display_tz) if display_tz is not None else first_dt
    when_str = f"{display_dt.strftime('%d.%m %H:%M')} {timezone_label(display_tz_name)}"
    human = format_recurring_human(pattern_type, payload)

    created_actions_keyboard = build_created_reminder_actions_keyboard(
        reminder_id,
        is_recurring=True,
    )
    sent_message = await safe_reply(
        message,
        format_created_recurring_reminder_text(
            when_str,
            text,
            human,
            chat_alias=used_alias,
        ),
        reply_markup=created_actions_keyboard,
    )

    _register_created_message(
        register_reminder_message,
        reminder_id=reminder_id,
        sent_message=sent_message,
        fallback_message=message,
    )
    return True
