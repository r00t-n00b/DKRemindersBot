"""Next/this weekday/month/week parser helpers."""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from parser_lexicon import NEXT_WORDS, THIS_WORDS, WEEKDAY_EN, WEEKDAY_RU
from parser_time_tokens import _extract_time_from_tokens


TZ = ZoneInfo("Europe/Madrid")
SYSTEM_DEFAULT_REMINDER_HOUR = 10
SYSTEM_DEFAULT_REMINDER_MINUTE = 0


def _default_time_or(value: Optional[Tuple[int, int]], fallback_hour: int, fallback_minute: int) -> Tuple[int, int]:
    return value if value is not None else (fallback_hour, fallback_minute)


def _parse_next_expression(expr: str, now: datetime, default_time: Optional[Tuple[int, int]] = None) -> Optional[datetime]:
    s = expr.lower().strip()
    tokens = s.split()
    if not tokens:
        return None

    local = now.astimezone(TZ)

    next_words = NEXT_WORDS
    this_words = THIS_WORDS

    # Русские предлоги не должны менять смысл:
    # "в следующую среду" == "следующую среду"
    # "на следующей неделе" == "следующей неделе"
    # "в четверг" == "четверг"
    if len(tokens) >= 2 and tokens[0] in {"в", "во", "на"}:
        tokens = tokens[1:]

    first = tokens[0]

    # Определяем режим:
    # - "next X" -> строго следующий (не сегодня)
    # - "this/coming/этот/ближайший X" -> ближайший (может быть сегодня)
    # - "X" где X weekday -> ближайший (может быть сегодня)
    mode: Optional[str] = None  # "next" | "this"
    start_idx = 0

    if first in next_words:
        mode = "next"
        start_idx = 1
    elif first in this_words:
        mode = "this"
        start_idx = 1
    else:
        # без префикса: попробуем weekday
        mode = "this"
        start_idx = 0

    if start_idx >= len(tokens):
        return None

    second = tokens[start_idx]

    # next week / следующая неделя
    if mode in {"next", "this"} and second in {"week", "неделя", "неделю", "неделе", "недели"}:
        base = local.date()
        cur_wd = base.weekday()
        days_until_next_monday = (7 - cur_wd) % 7

        if mode == "next":
            if days_until_next_monday == 0:
                days_until_next_monday = 7
        else:
            # this/coming week -> если сегодня пн, то сегодня (delta 0)
            # иначе ближайший понедельник (может быть через несколько дней)
            # (то есть фактически то же, что days_until_next_monday, но 0 разрешаем)
            pass

        rest_tokens = tokens[start_idx + 1 :]
        rest_tokens, hour, minute = _extract_time_from_tokens(rest_tokens, *_default_time_or(default_time, SYSTEM_DEFAULT_REMINDER_HOUR, SYSTEM_DEFAULT_REMINDER_MINUTE))
        target_date = base + timedelta(days=days_until_next_monday)
        return datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=TZ)

    # next month / следующий месяц
    if mode in {"next", "this"} and second in {"month", "месяц", "месяца"}:
        rest_tokens = tokens[start_idx + 1 :]
        rest_tokens, hour, minute = _extract_time_from_tokens(rest_tokens, *_default_time_or(default_time, SYSTEM_DEFAULT_REMINDER_HOUR, SYSTEM_DEFAULT_REMINDER_MINUTE))
        year = local.year
        month = local.month + 1 if mode == "next" else local.month

        if mode == "this":
            # this month -> сегодня, но час/минуты ставим на сегодня (если время уже прошло - завтра)
            dt = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if dt <= now:
                dt = dt + timedelta(days=1)
            return dt

        if month > 12:
            month = 1
            year += 1
        day = local.day
        while day > 28:
            try:
                return datetime(year, month, day, hour, minute, tzinfo=TZ)
            except ValueError:
                day -= 1
        return datetime(year, month, day, hour, minute, tzinfo=TZ)

    # weekday (en/ru)
    target_wd: Optional[int] = None
    rest_tokens: List[str] = []

    if second in WEEKDAY_EN:
        target_wd = WEEKDAY_EN[second]
        rest_tokens = tokens[start_idx + 1 :]
    elif second in WEEKDAY_RU:
        target_wd = WEEKDAY_RU[second]
        rest_tokens = tokens[start_idx + 1 :]
    else:
        return None

    rest_tokens, hour, minute = _extract_time_from_tokens(rest_tokens, *_default_time_or(default_time, SYSTEM_DEFAULT_REMINDER_HOUR, SYSTEM_DEFAULT_REMINDER_MINUTE))

    base_date = local.date()
    cur_wd = base_date.weekday()
    delta = (target_wd - cur_wd + 7) % 7

    candidate = datetime(base_date.year, base_date.month, base_date.day, hour, minute, tzinfo=TZ) + timedelta(days=delta)

    if mode == "next":
        # строго следующий: если попали на сегодня, уходим на +7
        if delta == 0:
            candidate = candidate + timedelta(days=7)
        return candidate

    # this/coming/без префикса: сегодня разрешаем, но только если время впереди
    if candidate <= now:
        candidate = candidate + timedelta(days=7)
    return candidate
