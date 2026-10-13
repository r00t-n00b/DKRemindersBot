"""Extract deterministic reminder context from a replied-to Telegram message."""

import re
from dataclasses import dataclass
from typing import Optional


_CONTEXT_REFERENCE_RE = re.compile(
    r"""
    \b(
        об\s+этом\s+сообщени[ие]
        |про\s+это\s+сообщение
        |это\s+сообщение
        |об\s+этом
        |про\s+это
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class ReplyReminderContext:
    text: str
    source_message_id: Optional[int] = None
    source_chat_id: Optional[int] = None


def refers_to_reply_context(text: str) -> bool:
    return bool(_CONTEXT_REFERENCE_RE.search(str(text or "")))


def _clean(value) -> str:
    return " ".join(str(value or "").split()).strip()


def _source_ids(message):
    message_id = getattr(message, "message_id", None)

    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)

    if chat_id is None:
        chat_id = getattr(message, "chat_id", None)

    return message_id, chat_id


def extract_reply_reminder_context(command_message) -> Optional[ReplyReminderContext]:
    source = getattr(command_message, "reply_to_message", None)
    if source is None:
        return None

    source_message_id, source_chat_id = _source_ids(source)

    text = _clean(getattr(source, "text", None))
    if text:
        return ReplyReminderContext(
            text=text,
            source_message_id=source_message_id,
            source_chat_id=source_chat_id,
        )

    caption = _clean(getattr(source, "caption", None))
    document = getattr(source, "document", None)
    filename = _clean(getattr(document, "file_name", None)) if document else ""

    if filename and caption:
        description = f"{filename}: {caption}"
    elif filename:
        description = filename
    elif caption:
        description = caption
    elif getattr(source, "photo", None):
        description = "фото"
    elif getattr(source, "video", None):
        description = "видео"
    elif getattr(source, "voice", None):
        description = "голосовое сообщение"
    elif getattr(source, "audio", None):
        description = "аудио"
    elif getattr(source, "animation", None):
        description = "анимация"
    elif getattr(source, "sticker", None):
        description = "стикер"
    else:
        description = "сообщение"

    forward_origin = getattr(source, "forward_origin", None)
    if forward_origin is not None:
        sender_name = _clean(getattr(forward_origin, "sender_user_name", None))
        if not sender_name:
            sender = getattr(forward_origin, "sender_user", None)
            sender_name = _clean(
                getattr(sender, "full_name", None)
                or getattr(sender, "username", None)
            )
        if sender_name:
            description = f"{description} от {sender_name}"

    return ReplyReminderContext(
        text=description,
        source_message_id=source_message_id,
        source_chat_id=source_chat_id,
    )


def replace_reply_context_reference(command_text: str, source_text: str) -> str:
    source_text = _clean(source_text)
    if not source_text:
        return str(command_text or "")

    return _CONTEXT_REFERENCE_RE.sub(
        source_text,
        str(command_text or ""),
        count=1,
    )
