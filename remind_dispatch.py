"""Dispatch normalized /remind arguments to bulk, recurring, or one-off creation."""

from typing import List


async def dispatch_remind_creation(
    *,
    had_newline: bool,
    raw_args: str,
    now,
    target_chat_id: int,
    used_alias,
    chat,
    user,
    message,
    is_private: bool,
    default_time,
    private_chat_type,
    looks_like_recurring,
    drop_optional_bulk_header,
    create_single_reminder_from_line,
    format_bulk_result,
    try_handle_single_recurring_reminder,
    handle_single_oneoff_reminder,
    parse_with_optional_default_time,
    parse_recurring,
    create_recurring_template,
    add_reminder,
    build_created_reminder_actions_keyboard,
    format_recurring_human,
    format_created_recurring_reminder_text,
    msg_recurring_parse_failed,
    parse_date_time_smart,
    normalize_plain_text_reminder_with_gemini,
    normalize_gemini_reminder_command_text,
    normalize_reminder_text_fallback,
    format_created_reminder_text,
    msg_parse_date_text_failed,
    safe_reply,
    logger,
) -> None:
    if had_newline:
        raw_lines = [ln.strip() for ln in raw_args.splitlines() if ln.strip()]

        # Поддержка bulk без "- ":
        # - если первая строка не похожа на напоминание и есть другие строки,
        #   считаем ее "заголовком" и пропускаем (пример: "Каталония")
        raw_lines = drop_optional_bulk_header(
            raw_lines,
            looks_like_recurring=looks_like_recurring,
        )

        lines = []
        for ln in raw_lines:
            ln2 = ln
            if ln2.startswith("-"):
                ln2 = ln2[1:].lstrip()
            lines.append(ln2)

        created = 0
        failed = 0
        error_lines: List[tuple[int, str, str]] = []

        for idx, line in enumerate(lines, start=1):
            original_line = line

            if line.startswith("-"):
                line = line[1:].lstrip()

            try:
                create_single_reminder_from_line(
                    line=line,
                    now=now,
                    target_chat_id=target_chat_id,
                    user=user,
                )
                created += 1
            except Exception as e:
                failed += 1
                error_lines.append((idx, original_line, str(e)))

        reply = format_bulk_result(
            created=created,
            failed=failed,
            error_lines=error_lines,
        )

        await safe_reply(message, reply)
        return

    raw_single = raw_args.strip()

    recurring_handled = await try_handle_single_recurring_reminder(
        raw_single=raw_single,
        now=now,
        target_chat_id=target_chat_id,
        used_alias=used_alias,
        chat=chat,
        user=user,
        message=message,
        is_private=is_private,
        default_time=default_time,
        looks_like_recurring=looks_like_recurring,
        parse_with_optional_default_time=parse_with_optional_default_time,
        parse_recurring=parse_recurring,
        create_recurring_template=create_recurring_template,
        add_reminder=add_reminder,
        build_created_reminder_actions_keyboard=build_created_reminder_actions_keyboard,
        format_recurring_human=format_recurring_human,
        format_created_recurring_reminder_text=format_created_recurring_reminder_text,
        msg_recurring_parse_failed=msg_recurring_parse_failed,
        safe_reply=safe_reply,
        logger=logger,
    )
    if recurring_handled:
        return

    await handle_single_oneoff_reminder(
        raw_single=raw_single,
        now=now,
        target_chat_id=target_chat_id,
        used_alias=used_alias,
        chat=chat,
        user=user,
        message=message,
        default_time=default_time,
        private_chat_type=private_chat_type,
        parse_with_optional_default_time=parse_with_optional_default_time,
        parse_date_time_smart=parse_date_time_smart,
        normalize_plain_text_reminder_with_gemini=normalize_plain_text_reminder_with_gemini,
        normalize_gemini_reminder_command_text=normalize_gemini_reminder_command_text,
        normalize_reminder_text_fallback=normalize_reminder_text_fallback,
        add_reminder=add_reminder,
        build_created_reminder_actions_keyboard=build_created_reminder_actions_keyboard,
        format_created_reminder_text=format_created_reminder_text,
        msg_parse_date_text_failed=msg_parse_date_text_failed,
        safe_reply=safe_reply,
        logger=logger,
    )
