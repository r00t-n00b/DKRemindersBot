"""Plain text reminder command flow."""

from typing import Any, Dict, List, Optional, Tuple

from dkreminders_bot.commands.reply_reminder_context import (
    extract_message_reminder_context,
    extract_reply_reminder_context,
    refers_to_reply_context,
    replace_reply_context_reference,
    summarize_reply_context,
)


_DEP_NAMES = [
    "Chat",
    "MSG_NOT_UNDERSTOOD_PLAIN_TEXT",
    "NormalizedReminderMessageProxy",
    "SimpleNamespace",
    "_normalize_plain_text_relative_reminder_locally",
    "_normalize_plain_text_reminder_locally",
    "_normalize_reminder_text_fallback",
    "logger",
    "normalize_gemini_reminder_command_text",
    "normalize_plain_text_reminder_with_gemini",
    "remind_command",
    "safe_reply",
    "type",
]


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


def _is_temporary_gemini_text_failure(exc: Exception) -> bool:
    return type(exc).__name__ == "GeminiTextNormalizationTemporaryError"


AI_TEMPORARY_FAILURE_FALLBACK_TEXT = (
    "Сейчас не смог обработать текст: сервис распознавания временно перегружен.\n"
    "Попробуй ещё раз через несколько секунд или напиши явно:\n"
    "/remind через час - добить трейды"
)


async def handle_plain_text_remind_command(update, context, deps) -> None:
    _apply_deps(deps)
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    # Обычный свободный текст обрабатываем только в личке.
    # В группах нельзя, иначе бот будет реагировать на обычную переписку.
    if chat.type != Chat.PRIVATE:
        return

    raw_text = (getattr(message, "text", "") or "").strip()
    if not raw_text:
        return

    if raw_text.startswith("/"):
        return

    reply_context = None
    if refers_to_reply_context(raw_text):
        reply_context = extract_reply_reminder_context(message)
        if reply_context is None:
            context.user_data["pending_forward_comment_reminder"] = {
                "raw_text": raw_text,
                "command_message": message,
            }
            return

    get_user_timezone_name_raw = getattr(deps, "get_user_timezone_name_raw", None)
    build_first_timezone_prompt = getattr(deps, "build_first_timezone_prompt", None)
    build_timezone_picker_keyboard = getattr(deps, "build_timezone_picker_keyboard", None)

    if (
        callable(get_user_timezone_name_raw)
        and callable(build_first_timezone_prompt)
        and callable(build_timezone_picker_keyboard)
        and get_user_timezone_name_raw(user.id) is None
    ):
        context.user_data["pending_plain_text_reminder_after_timezone"] = raw_text
        await safe_reply(
            message,
            build_first_timezone_prompt(),
            reply_markup=build_timezone_picker_keyboard(),
        )
        return

    normalization_source = "local"
    normalized = _normalize_plain_text_reminder_locally(raw_text)

    if not normalized:
        normalization_source = "local_relative"
        normalized = _normalize_plain_text_relative_reminder_locally(raw_text)

    if not normalized:
        normalization_source = "gemini"
        try:
            normalized = await normalize_plain_text_reminder_with_gemini(raw_text, user.id)
        except Exception as e:
            if _is_temporary_gemini_text_failure(e):
                logger.warning(
                    "TEXT_REMIND_AI_TEMPORARY_FAILURE user_id=%s chat_id=%s error_type=%s error=%s raw_text=%r",
                    user.id,
                    chat.id,
                    type(e).__name__,
                    e,
                    raw_text,
                )
                await safe_reply(
                    message,
                    getattr(
                        deps,
                        "MSG_PLAIN_TEXT_AI_TEMPORARY_FAILURE",
                        AI_TEMPORARY_FAILURE_FALLBACK_TEXT,
                    ),
                )
                return

            logger.exception(
                "TEXT_REMIND_FAILED user_id=%s chat_id=%s error_type=%s error=%s raw_text=%r",
                user.id,
                chat.id,
                type(e).__name__,
                e,
                raw_text,
            )
            normalization_source = "fallback"
            normalized = _normalize_reminder_text_fallback(raw_text)

    normalized = (normalized or "").strip()
    normalized = normalize_gemini_reminder_command_text(normalized)

    if reply_context is not None and normalized and normalized != "NO_REMINDER":
        source_context_text = await summarize_reply_context(
            reply_context.text,
            normalize_with_gemini=normalize_plain_text_reminder_with_gemini,
            created_by=user.id,
        )
        normalized = replace_reply_context_reference(
            normalized,
            source_context_text,
        )

    if (
        reply_context is None
        and not getattr(message, "reply_to_message", None)
        and normalized
        and normalized != "NO_REMINDER"
        and normalized.rstrip().endswith("-")
    ):
        pending_when = normalized.rstrip()[:-1].strip()
        if pending_when:
            context.user_data["pending_forward_comment_reminder"] = {
                "raw_text": raw_text,
                "command_message": message,
            }
            return

    if normalized == "NO_REMINDER" or not normalized:
        await safe_reply(
            message,
            MSG_NOT_UNDERSTOOD_PLAIN_TEXT
        )
        return


    if normalized.startswith("/remind "):
        normalized = normalized[len("/remind "):].strip()

    logger.info(
        "TEXT_REMIND_NORMALIZED source=%s user_id=%s chat_id=%s raw_len=%s normalized_len=%s",
        normalization_source,
        user.id,
        chat.id,
        len(raw_text),
        len(normalized),
    )

    if " - " not in normalized:
        normalized = _normalize_reminder_text_fallback(normalized)

    if not normalized or " - " not in normalized:
        await safe_reply(
            message,
            MSG_NOT_UNDERSTOOD_PLAIN_TEXT
        )
        return

    proxy_message = NormalizedReminderMessageProxy(
        message,
        f"/remind {normalized}",
        normalized,
        suppress_normalized_prefix=reply_context is not None,
    )

    proxy_update = SimpleNamespace(
        effective_chat=chat,
        effective_message=proxy_message,
        effective_user=user,
        message=proxy_message,
    )

    await remind_command(proxy_update, context)
