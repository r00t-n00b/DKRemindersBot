"""Plain text reminder command flow."""

from typing import Any, Dict, List, Optional, Tuple


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
    )

    proxy_update = SimpleNamespace(
        effective_chat=chat,
        effective_message=proxy_message,
        effective_user=user,
        message=proxy_message,
    )

    await remind_command(proxy_update, context)
