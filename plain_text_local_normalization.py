"""Local plain-text reminder normalization before Gemini fallback."""

import re
from typing import Optional


def normalize_plain_text_reminder_locally(
    raw_text: str,
    *,
    split_expr_and_text,
    parse_date_time_smart,
    get_now,
) -> Optional[str]:
    """Fast local path for plain text reminders before Gemini.

    Converts simple natural messages like:
    "напомни 1 октября пересчитать страховку"
    into:
    "1 октября - пересчитать страховку"

    Returns None if local parser cannot confidently split date/time and text.
    """
    candidate = (raw_text or "").strip()
    if not candidate:
        return None

    candidate = re.sub(
        r"^\s*(?:напомни(?:\s+мне)?|напомнить(?:\s+мне)?|remind(?:\s+me)?(?:\s+to)?)\s+",
        "",
        candidate,
        flags=re.IGNORECASE,
    ).strip()

    if not candidate:
        return None

    # Keep this local fast path deliberately narrow.
    # Broader phrases like "напомни завтра поздравить Саню" should still go to Gemini,
    # because Gemini may add useful default time details such as 18:00.
    m = re.match(
        r"^\s*((?:сегодня|завтра|послезавтра|today|tomorrow|day after tomorrow)\s+(?:в|at)\s+\d{1,2}[:.]\d{2})\s+(.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if m:
        expr = re.sub(r"\s+(?:в|at)\s+", " ", m.group(1).strip(), flags=re.IGNORECASE)
        reminder_text = m.group(2).strip()
        if not expr or not reminder_text:
            return None
        try:
            parse_date_time_smart(f"{expr} - {reminder_text}", get_now())
        except Exception:
            return None
        return f"{expr} - {reminder_text}"

    if not re.match(
        r"^\s*\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)(?:\s+(?:в\s+)?\d{1,2}[:.]\d{2})?\s+.+$",
        candidate,
        flags=re.IGNORECASE,
    ):
        return None

    try:
        expr, reminder_text = split_expr_and_text(candidate)
        parse_date_time_smart(candidate, get_now())
    except Exception:
        return None

    expr = expr.strip()
    reminder_text = reminder_text.strip()
    if not expr or not reminder_text:
        return None

    return f"{expr} - {reminder_text}"
