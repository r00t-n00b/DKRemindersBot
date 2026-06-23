"""Source chat helpers for self-remind flow."""

from typing import Any


def format_self_remind_text(source_chat_title: str, source_text: str) -> str:
    return f'Из чата "{source_chat_title}": {source_text}'


def get_query_source_chat_title(query) -> str:
    source_chat_title = "этого чата"
    if getattr(query, "message", None) is not None:
        chat_obj = getattr(query.message, "chat", None)
        if chat_obj is not None:
            source_chat_title = (
                getattr(chat_obj, "title", None)
                or getattr(chat_obj, "full_name", None)
                or "этого чата"
            )
    return source_chat_title


async def get_source_chat_title_for_self_remind(context: Any, src: Any, query: Any) -> str:
    try:
        chat = await context.bot.get_chat(src.chat_id)
        return (
            getattr(chat, "title", None)
            or getattr(chat, "full_name", None)
            or getattr(chat, "username", None)
            or f"chat {src.chat_id}"
        )
    except Exception:
        return get_query_source_chat_title(query)
