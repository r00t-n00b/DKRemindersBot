"""Bounded plain-text diagnostic output, including safe error summaries."""

import re
import unicodedata

from dkreminders_bot.ui.messages import DIAGNOSTICS_TEXT as T

PAGE_SIZE = 5


def _clip(value, limit):
    value = " ".join("".join(c if not unicodedata.category(c).startswith("C") else " " for c in str(value)).split())
    raw = value.encode("utf-16-le")
    return value if len(raw) <= limit * 2 else raw[:(limit-1)*2].decode("utf-16-le", errors="ignore") + "…"


def _error(value, secrets):
    text = str(value or T["none"])
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[скрыто]")
    text = re.sub(r"(?<![0-9])\d{5,}:[A-Za-z0-9_-]{20,}", "[скрыто]", text)
    text = re.sub(r"AIza[A-Za-z0-9_-]{20,}", "[скрыто]", text)
    return _clip(text, 100)


def diagnostic_row(row, *, secrets=()):
    def field(key, limit=40):
        value = row.get(key)
        return _clip(value, limit) if value is not None and value != "" else T["none"]

    tracked = row["tracked"]
    source = T["none"] if row.get("source_message_id") is None else f"{field('source_chat_id')}/{field('source_message_id')}"
    return T["row"].format(
        id=row["id"], status=T["done"] if row["acked"] else T["delivered"] if row["delivered"] else T["pending"],
        text=field("text", 80), chat_id=field("chat_id"), template_id=field("template_id"),
        created_at=field("created_at"), remind_at=field("remind_at"), timezone=field("timezone_name"),
        delivered=T["yes"] if row["delivered"] else T["no"], acked=T["yes"] if row["acked"] else T["no"],
        sent_at=field("sent_at"), nudges=field("nudge_count"), last_nudge=field("last_nudge_at"),
        state=field("delivery_state", 24), attempts=field("delivery_attempts"), retry=field("next_retry_at"),
        created=tracked.get("created", 0), delivery=tracked.get("delivery", 0), nudge_messages=tracked.get("nudge", 0),
        source=source, error=_error(row.get("last_error"), secrets),
    )


def diagnostic_page(rows, page=0, *, target=None, secrets=()):
    pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages-1))
    header = T["header"].format(target=_clip(target, 60) if target else T["all"], count=len(rows), page=page+1, pages=pages)
    blocks = [diagnostic_row(row, secrets=secrets) for row in rows[page*PAGE_SIZE:(page+1)*PAGE_SIZE]]
    text = header + "\n\n" + ("\n\n".join(blocks) if blocks else T["empty"]) + "\n\n" + T["note"]
    return text, page, pages
