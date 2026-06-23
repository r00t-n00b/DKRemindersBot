"""Handle one-line recurring /remind flow."""


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

    when_str = first_dt.strftime("%d.%m %H:%M")
    human = format_recurring_human(pattern_type, payload)

    created_actions_keyboard = build_created_reminder_actions_keyboard(
        reminder_id,
        is_recurring=True,
    )
    await safe_reply(
        message,
        format_created_recurring_reminder_text(
            when_str,
            text,
            human,
            chat_alias=used_alias,
        ),
        reply_markup=created_actions_keyboard,
    )
    return True
