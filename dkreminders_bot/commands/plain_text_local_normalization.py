"""Local plain-text reminder normalization before Gemini fallback."""

import re
from typing import Optional

from dkreminders_bot.parsing.parser_lexicon import MONTH_EN, WEEKDAY_EN, WEEKDAY_RU


RU_MONTHS = (
    "января|февраля|марта|апреля|мая|июня|июля|августа|"
    "сентября|октября|ноября|декабря"
)


def _strip_plain_text_reminder_prefix(raw_text: str) -> str:
    return re.sub(
        r"^\s*(?:напомни(?:\s+мне)?|напомнить(?:\s+мне)?|remind(?:\s+me)?(?:\s+to)?)\s+",
        "",
        raw_text,
        flags=re.IGNORECASE,
    ).strip()


def _format_time(hour_raw: str, minute_raw: str | None) -> Optional[str]:
    hour = int(hour_raw)
    minute = int(minute_raw or "0")
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return f"{hour}:{minute:02d}"


def _validated(expr: str, reminder_text: str, *, parse_date_time_smart, get_now) -> Optional[str]:
    expr = (expr or "").strip()
    reminder_text = (reminder_text or "").strip()
    if not expr or not reminder_text:
        return None

    normalized = f"{expr} - {reminder_text}"
    try:
        parse_date_time_smart(normalized, get_now())
    except Exception:
        return None
    return normalized


def normalize_plain_text_reminder_locally(
    raw_text: str,
    *,
    split_expr_and_text,
    parse_date_time_smart,
    get_now,
) -> Optional[str]:
    """Fast local path for explicit plain-text reminders before Gemini.

    Keeps broad ambiguous phrases on Gemini, but handles deterministic cases:
    - "напомни в 13.46 рейд" -> "13:46 - рейд"
    - "напомни завтра 13.46 рейд" -> "завтра 13:46 - рейд"
    - "напомни 1 октября в 13.46 страховка" -> "1 октября в 13:46 - страховка"
    """

    candidate = (raw_text or "").strip()
    if not candidate:
        return None

    candidate = _strip_plain_text_reminder_prefix(candidate)
    if not candidate:
        return None

    m = re.match(
        r"^\s*(?P<date>сегодня|завтра|послезавтра|today|tomorrow|day after tomorrow)\s+"
        r"(?:(?:в|at)\s+)?"
        r"(?P<hour>\d{1,2})(?:(?:[:.])(?P<minute>\d{2}))?\s+"
        r"(?P<text>.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if m:
        time_value = _format_time(m.group("hour"), m.group("minute"))
        if time_value:
            return _validated(
                f"{m.group('date')} {time_value}",
                m.group("text"),
                parse_date_time_smart=parse_date_time_smart,
                get_now=get_now,
            )

    m = re.match(
        r"^\s*(?:в\s+)?(?P<next>следующий|следующая|следующее|следующие|next)\s+"
        r"(?P<weekday>[a-zа-яё]+)\s+"
        r"(?:(?:в|at)\s+)?"
        r"(?P<hour>\d{1,2})(?:(?:[:.])(?P<minute>\d{2}))?\s+"
        r"(?P<text>.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if m:
        weekday = m.group("weekday").lower()
        if weekday in WEEKDAY_EN or weekday in WEEKDAY_RU:
            time_value = _format_time(m.group("hour"), m.group("minute"))
            if time_value:
                return _validated(
                    f"{m.group('next')} {weekday} {time_value}",
                    m.group("text"),
                    parse_date_time_smart=parse_date_time_smart,
                    get_now=get_now,
                )

    m = re.match(
        r"^\s*(?:в\s+)?(?P<weekday>[a-zа-яё]+)\s+"
        r"(?:(?:в|at)\s+)?"
        r"(?P<hour>\d{1,2})(?:(?:[:.])(?P<minute>\d{2}))?\s+"
        r"(?P<text>.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if m:
        weekday = m.group("weekday").lower()
        if weekday in WEEKDAY_EN or weekday in WEEKDAY_RU:
            time_value = _format_time(m.group("hour"), m.group("minute"))
            if time_value:
                return _validated(
                    f"в {weekday} {time_value}",
                    m.group("text"),
                    parse_date_time_smart=parse_date_time_smart,
                    get_now=get_now,
                )

    m = re.match(
        rf"^\s*(?P<day>\d{{1,2}})\s+(?P<month>{RU_MONTHS})\s+"
        rf"(?:(?:в)\s+)?(?P<hour>\d{{1,2}})(?:(?:[:.])(?P<minute>\d{{2}}))\s+"
        rf"(?P<text>.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if m:
        time_value = _format_time(m.group("hour"), m.group("minute"))
        if time_value:
            return _validated(
                f"{m.group('day')} {m.group('month')} в {time_value}",
                m.group("text"),
                parse_date_time_smart=parse_date_time_smart,
                get_now=get_now,
            )

    m = re.match(
        rf"^\s*(?P<day>\d{{1,2}})\s+(?P<month>{RU_MONTHS})\s+(?P<text>.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if m:
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

    m = re.match(
        r"^\s*(?P<day>\d{1,2})\s+(?P<month>[a-z]+)\s+"
        r"(?:(?:at)\s+)?(?P<hour>\d{1,2})(?:(?:[:.])(?P<minute>\d{2}))\s+"
        r"(?P<text>.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if m and m.group("month").lower() in MONTH_EN:
        time_value = _format_time(m.group("hour"), m.group("minute"))
        if time_value:
            return _validated(
                f"{m.group('day')} {m.group('month')} {time_value}",
                m.group("text"),
                parse_date_time_smart=parse_date_time_smart,
                get_now=get_now,
            )

    m = re.match(
        r"^\s*(?P<day>\d{1,2})\s+(?P<month>[a-z]+)\s+(?P<text>.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if m and m.group("month").lower() in MONTH_EN:
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

    m = re.match(
        r"^\s*(?:(?:в|at)\s+)?"
        r"(?P<hour>\d{1,2})(?:[:.])(?P<minute>\d{2})\s+"
        r"(?P<text>.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if m:
        time_value = _format_time(m.group("hour"), m.group("minute"))
        if time_value:
            return _validated(
                time_value,
                m.group("text"),
                parse_date_time_smart=parse_date_time_smart,
                get_now=get_now,
            )

    m = re.match(
        r"^\s*(?:в|at)\s+"
        r"(?P<hour>\d{1,2})\s+"
        r"(?P<text>.+)$",
        candidate,
        flags=re.IGNORECASE,
    )
    if m:
        time_value = _format_time(m.group("hour"), None)
        if time_value:
            return _validated(
                time_value,
                m.group("text"),
                parse_date_time_smart=parse_date_time_smart,
                get_now=get_now,
            )

    return None
