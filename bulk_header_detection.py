"""Bulk reminder header detection helpers."""

import re


def bulk_line_looks_like_reminder_start(line: str, *, looks_like_recurring) -> bool:
    first = (line or "").lstrip("-").strip()

    if not first:
        return False

    if looks_like_recurring(first):
        return True

    # Heuristic: строка похожа на одноразовое напоминание, если начинается с "даты/времени"
    # или с month-name формата ("On March 1 ...", "March 1 ..."), или с relative ("in 2 hours ...").
    return bool(
        re.match(
            r"^(?:"
            r"(?:on\s+)?\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?(?:\s+\d{1,2}[:.]\d{2})?"
            r"|"
            r"\d{1,2}[:.]\d{2}"
            r"|"
            r"(?:today|tomorrow|day\s+after\s+tomorrow|сегодня|завтра|послезавтра)(?:\s+\d{1,2}[:.]\d{2})?"
            r"|"
            r"(?:in|через)\s+\d+\s+\w+"
            r"|"
            r"(?:on\s+)?[A-Za-z]{3,9}\s+\d{1,2}(?:\s+\d{4})?(?:\s+\d{1,2}[:.]\d{2})?"
            r")\b",
            first,
            flags=re.IGNORECASE,
        )
    )


def drop_optional_bulk_header(raw_lines, *, looks_like_recurring):
    lines = list(raw_lines or [])

    if len(lines) <= 1:
        return lines

    if bulk_line_looks_like_reminder_start(
        lines[0],
        looks_like_recurring=looks_like_recurring,
    ):
        return lines

    return lines[1:]
