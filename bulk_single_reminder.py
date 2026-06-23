"""Create one bulk reminder line as oneoff or recurring."""


def create_single_reminder_from_line(
    *,
    line: str,
    now,
    target_chat_id: int,
    user,
    default_time=None,
    looks_like_recurring,
    parse_with_optional_default_time,
    parse_recurring,
    parse_date_time_smart,
    create_recurring_template,
    add_reminder,
    logger,
):
    """
    Создает одно напоминание (oneoff или recurring) из строки.
    Бросает исключение при ошибке.
    """
    if looks_like_recurring(line):
        first_dt, text, pattern_type, payload, hour, minute = parse_with_optional_default_time(
            parse_recurring,
            line,
            now,
            default_time=default_time,
        )

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
            "Создан bulk recurring reminder id=%s tpl_id=%s chat_id=%s at=%s text=%s",
            reminder_id,
            tpl_id,
            target_chat_id,
            first_dt.isoformat(),
            text,
        )
    else:
        remind_at, text = parse_with_optional_default_time(
            parse_date_time_smart,
            line,
            now,
            default_time=default_time,
        )

        reminder_id = add_reminder(
            chat_id=target_chat_id,
            text=text,
            remind_at=remind_at,
            created_by=user.id,
        )

        logger.info(
            "Создан bulk reminder id=%s chat_id=%s at=%s text=%s",
            reminder_id,
            target_chat_id,
            remind_at.isoformat(),
            text,
        )
