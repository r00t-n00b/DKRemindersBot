"""Handle one-line oneoff /remind flow."""

from messages import msg_created_for_alias_chat, msg_created_for_other_user

import asyncio
import logging
import os

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


async def handle_single_oneoff_reminder(
    *,
    raw_single: str,
    now,
    target_chat_id: int,
    used_alias,
    chat,
    user,
    message,
    default_time,
    private_chat_type,
    parse_with_optional_default_time,
    parse_date_time_smart,
    normalize_plain_text_reminder_with_gemini,
    normalize_gemini_reminder_command_text,
    normalize_reminder_text_fallback,
    add_reminder,
    build_created_reminder_actions_keyboard,
    format_created_reminder_text,
    msg_parse_date_text_failed: str,
    safe_reply,
    logger,
    register_reminder_message=None,
):
    try:
        remind_at, text = parse_with_optional_default_time(
            parse_date_time_smart,
            raw_single,
            now,
            default_time=default_time,
        )
    except ValueError as e:
        original_error = e
        normalized_single = None

        try:
            created_by = user.id if user else None
            try:
                gemini_result = await asyncio.wait_for(
                    normalize_plain_text_reminder_with_gemini(raw_single, created_by),
                    timeout=float(os.environ.get("GEMINI_REMINDER_PARSE_TIMEOUT_SECONDS", "10")),
                )
            except asyncio.TimeoutError:
                logging.warning(
                    "REMIND Gemini fallback timed out user=%s chat=%s raw=%r",
                    getattr(user, "id", None),
                    chat.id,
                    raw_single,
                )
                raise original_error

            if gemini_result and gemini_result.strip().upper() != "NO_REMINDER":
                normalized_single = gemini_result.strip()

                if normalized_single.startswith("/remind"):
                    normalized_single = normalized_single[len("/remind"):].strip()

                normalized_single = normalize_gemini_reminder_command_text(normalized_single)
                normalized_single = normalize_reminder_text_fallback(normalized_single)

                if normalized_single.startswith("/remind"):
                    normalized_single = normalized_single[len("/remind"):].strip()

                remind_at, text = parse_with_optional_default_time(
                    parse_date_time_smart,
                    normalized_single,
                    now,
                    default_time=default_time,
                )
            else:
                raise original_error
        except Exception as fallback_error:
            logging.info(
                "REMIND parse failed user=%s chat=%s raw=%r normalized=%r error=%s fallback_error=%s",
                getattr(user, "id", None),
                chat.id,
                raw_single,
                normalized_single,
                original_error,
                fallback_error,
            )
            await safe_reply(message, msg_parse_date_text_failed)
            return

    reminder_id = add_reminder(
        chat_id=target_chat_id,
        text=text,
        remind_at=remind_at,
        created_by=user.id,
    )

    logger.info(
        "Создан reminder id=%s chat_id=%s at=%s text=%s (from chat %s, user %s)",
        reminder_id,
        target_chat_id,
        remind_at.isoformat(),
        text,
        chat.id,
        user.id,
    )

    display_tz = getattr(now, "tzinfo", None)
    display_tz_name = getattr(display_tz, "key", None)
    display_dt = remind_at.astimezone(display_tz) if display_tz is not None else remind_at
    when_str = f"{display_dt.strftime('%d.%m %H:%M')} {timezone_label(display_tz_name)}"
    created_actions_keyboard = build_created_reminder_actions_keyboard(reminder_id)
    sent_message = None
    if used_alias:
        sent_message = await safe_reply(
            message,
            msg_created_for_alias_chat(used_alias, when_str, text),
            reply_markup=created_actions_keyboard,
        )
    else:
        if target_chat_id != chat.id and chat.type == private_chat_type:
            sent_message = await safe_reply(
                message,
                msg_created_for_other_user(when_str, text),
                reply_markup=created_actions_keyboard,
            )
        else:
            sent_message = await safe_reply(
                message,
                format_created_reminder_text(when_str, text),
                reply_markup=created_actions_keyboard,
            )

    _register_created_message(
        register_reminder_message,
        reminder_id=reminder_id,
        sent_message=sent_message,
        fallback_message=message,
    )
