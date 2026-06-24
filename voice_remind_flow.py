"""Voice reminder command flow."""

from typing import Any, Dict, List, Optional, Tuple


_DEP_NAMES = [
    "Chat",
    "NormalizedReminderMessageProxy",
    "SimpleNamespace",
    "_normalize_reminder_text_fallback",
    "logger",
    "remind_command",
    "safe_reply",
    "transcribe_voice_message",
    "type",
]


def _apply_deps(deps) -> None:
    for name in _DEP_NAMES:
        globals()[name] = getattr(deps, name)


async def handle_voice_remind_command(update, context, deps) -> None:
    _apply_deps(deps)
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user

    if chat is None or message is None or user is None:
        return

    # В группах голосовые игнорируем, чтобы бот не слушал всё подряд.
    if chat.type != Chat.PRIVATE:
        return

    try:
        heard_text = await transcribe_voice_message(update, context)
    except Exception as e:
        logger.exception(
            "VOICE_REMIND_FAILED user_id=%s chat_id=%s error_type=%s error=%s",
            user.id,
            chat.id,
            type(e).__name__,
            e,
        )
        await safe_reply(
            message,
            "Не смог распознать голосовое: сервис распознавания сейчас перегружен. "
            "Попробуй еще раз чуть позже или напиши текстом."
        )
        return

    normalized = _normalize_reminder_text_fallback(heard_text)
    if not normalized:
        await safe_reply(message, "Не услышал текст в голосовом.")
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
