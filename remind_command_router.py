"""Router for the /remind command.

The router receives dependencies from main.py to keep this module independent
from the Telegram application wiring and easy to test.
"""


async def handle_remind_command(update, context, deps) -> None:
    Chat = deps.Chat
    MSG_GROUP_ALIAS_PREFIX_FORBIDDEN = deps.MSG_GROUP_ALIAS_PREFIX_FORBIDDEN
    MSG_GROUP_USERNAME_PREFIX_FORBIDDEN = deps.MSG_GROUP_USERNAME_PREFIX_FORBIDDEN
    MSG_PARSE_DATE_TEXT_FAILED = deps.MSG_PARSE_DATE_TEXT_FAILED
    MSG_REMIND_USAGE = deps.MSG_REMIND_USAGE
    _create_single_reminder_from_line = deps._create_single_reminder_from_line
    _format_bulk_result = deps._format_bulk_result
    _normalize_reminder_text_fallback = deps._normalize_reminder_text_fallback
    add_reminder = deps.add_reminder
    build_created_reminder_actions_keyboard = deps.build_created_reminder_actions_keyboard
    create_recurring_template = deps.create_recurring_template
    dispatch_remind_creation = deps.dispatch_remind_creation
    drop_optional_bulk_header = deps.drop_optional_bulk_header
    extract_after_command = deps.extract_after_command
    first_token_looks_like_reminder_start = deps.first_token_looks_like_reminder_start
    format_created_recurring_reminder_text = deps.format_created_recurring_reminder_text
    format_created_reminder_text = deps.format_created_reminder_text
    format_recurring_human = deps.format_recurring_human
    get_chat_id_by_alias_for_user = deps.get_chat_id_by_alias_for_user
    get_now = deps.get_now
    get_user_alias_chat_id_for_user = deps.get_user_alias_chat_id_for_user
    get_user_chat_id_by_username = deps.get_user_chat_id_by_username
    get_user_default_time = deps.get_user_default_time
    handle_single_oneoff_reminder = deps.handle_single_oneoff_reminder
    is_recurring_missing_dash_candidate = deps.is_recurring_missing_dash_candidate
    logger = deps.logger
    looks_like_recurring = deps.looks_like_recurring
    msg_after_me_requires_date_and_text = deps.msg_after_me_requires_date_and_text
    msg_after_target_requires_date_and_text = deps.msg_after_target_requires_date_and_text
    msg_recurring_missing_dash = deps.msg_recurring_missing_dash
    msg_recurring_parse_failed = deps.msg_recurring_parse_failed
    msg_user_has_not_started_bot = deps.msg_user_has_not_started_bot
    normalize_gemini_reminder_command_text = deps.normalize_gemini_reminder_command_text
    normalize_plain_text_reminder_with_gemini = deps.normalize_plain_text_reminder_with_gemini
    parse_date_time_smart = deps.parse_date_time_smart
    parse_recurring = deps.parse_recurring
    parse_with_optional_default_time = deps.parse_with_optional_default_time
    reject_group_remind_target_prefix_if_needed = deps.reject_group_remind_target_prefix_if_needed
    resolve_remind_target_and_args = deps.resolve_remind_target_and_args
    safe_reply = deps.safe_reply
    strip_first_token_from_first_line = deps.strip_first_token_from_first_line
    try_handle_single_recurring_reminder = deps.try_handle_single_recurring_reminder
    upsert_user_chat = deps.upsert_user_chat

    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    now = get_now()
    default_time = get_user_default_time(user.id)

    raw_text = message.text or ""

    logger.info(
        "REMIND input chat_id=%s chat_type=%s user_id=%s raw_text=%r",
        chat.id,
        chat.type,
        user.id,
        raw_text,
    )

    had_newline = "\n" in raw_text

    if had_newline:
        first_line, rest = raw_text.split("\n", 1)

        parts = first_line.split(maxsplit=1)
        first_line_args = parts[1] if len(parts) == 2 else ""

        # НЕ удаляем факт многострочности: bulk должен сработать даже если строка одна
        raw_args = (first_line_args + "\n" + rest).strip("\n")
    else:
        raw_args = extract_after_command(raw_text)

    if not raw_args.strip():
        await safe_reply(
            message,
            MSG_REMIND_USAGE,
        )
        return

    is_private = chat.type == Chat.PRIVATE

    group_prefix_rejected, raw_args = await reject_group_remind_target_prefix_if_needed(
        is_private=is_private,
        raw_args=raw_args,
        user_id=user.id,
        message=message,
        safe_reply=safe_reply,
        get_chat_id_by_alias_for_user=get_chat_id_by_alias_for_user,
        msg_group_username_prefix_forbidden=MSG_GROUP_USERNAME_PREFIX_FORBIDDEN,
        msg_group_alias_prefix_forbidden=MSG_GROUP_ALIAS_PREFIX_FORBIDDEN,
    )
    if group_prefix_rejected:
        return

    if is_recurring_missing_dash_candidate(raw_args) and " - " not in raw_args:
        await safe_reply(message, msg_recurring_missing_dash(is_private))
        return

    target_resolution = await resolve_remind_target_and_args(
        is_private=is_private,
        raw_args=raw_args,
        had_newline=had_newline,
        chat=chat,
        user=user,
        message=message,
        now=now,
        default_time=default_time,
        safe_reply=safe_reply,
        logger=logger,
        strip_first_token_from_first_line=strip_first_token_from_first_line,
        first_token_looks_like_reminder_start=first_token_looks_like_reminder_start,
        get_user_chat_id_by_username=get_user_chat_id_by_username,
        get_user_alias_chat_id_for_user=get_user_alias_chat_id_for_user,
        get_chat_id_by_alias_for_user=get_chat_id_by_alias_for_user,
        parse_with_optional_default_time=parse_with_optional_default_time,
        parse_date_time_smart=parse_date_time_smart,
        upsert_user_chat=upsert_user_chat,
        msg_after_me_requires_date_and_text=msg_after_me_requires_date_and_text,
        msg_user_has_not_started_bot=msg_user_has_not_started_bot,
        msg_after_target_requires_date_and_text=msg_after_target_requires_date_and_text,
    )
    if target_resolution.aborted:
        return

    raw_args = target_resolution.raw_args
    had_newline = target_resolution.had_newline
    target_chat_id = target_resolution.target_chat_id
    used_alias = target_resolution.used_alias

    await dispatch_remind_creation(
        had_newline=had_newline,
        raw_args=raw_args,
        now=now,
        target_chat_id=target_chat_id,
        used_alias=used_alias,
        chat=chat,
        user=user,
        message=message,
        is_private=is_private,
        default_time=default_time,
        private_chat_type=Chat.PRIVATE,
        looks_like_recurring=looks_like_recurring,
        drop_optional_bulk_header=drop_optional_bulk_header,
        create_single_reminder_from_line=_create_single_reminder_from_line,
        format_bulk_result=_format_bulk_result,
        try_handle_single_recurring_reminder=try_handle_single_recurring_reminder,
        handle_single_oneoff_reminder=handle_single_oneoff_reminder,
        parse_with_optional_default_time=parse_with_optional_default_time,
        parse_recurring=parse_recurring,
        create_recurring_template=create_recurring_template,
        add_reminder=add_reminder,
        build_created_reminder_actions_keyboard=build_created_reminder_actions_keyboard,
        format_recurring_human=format_recurring_human,
        format_created_recurring_reminder_text=format_created_recurring_reminder_text,
        msg_recurring_parse_failed=msg_recurring_parse_failed,
        parse_date_time_smart=parse_date_time_smart,
        normalize_plain_text_reminder_with_gemini=normalize_plain_text_reminder_with_gemini,
        normalize_gemini_reminder_command_text=normalize_gemini_reminder_command_text,
        normalize_reminder_text_fallback=_normalize_reminder_text_fallback,
        format_created_reminder_text=format_created_reminder_text,
        msg_parse_date_text_failed=MSG_PARSE_DATE_TEXT_FAILED,
        safe_reply=safe_reply,
        logger=logger,
    )
    return
