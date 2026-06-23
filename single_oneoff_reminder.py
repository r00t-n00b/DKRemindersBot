"""Handle one-line oneoff /remind flow."""

import asyncio
import logging
import os


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

    when_str = remind_at.strftime("%d.%m %H:%M")
    created_actions_keyboard = build_created_reminder_actions_keyboard(reminder_id)
    if used_alias:
        await safe_reply(
            message,
            f"Ок, напомню в чате '{used_alias}' {when_str}: {text}",
            reply_markup=created_actions_keyboard,
        )
    else:
        if target_chat_id != chat.id and chat.type == private_chat_type:
            await safe_reply(
                message,
                f"Ок, напомню этому человеку {when_str}: {text}",
                reply_markup=created_actions_keyboard,
            )
        else:
            await safe_reply(
                message,
                format_created_reminder_text(when_str, text),
                reply_markup=created_actions_keyboard,
            )
