"""Reply helper utilities."""

import inspect


async def safe_reply(message, text: str, **kwargs):
    if not message or not hasattr(message, "reply_text"):
        return

    res = message.reply_text(text, **kwargs)
    if inspect.isawaitable(res):
        await res
