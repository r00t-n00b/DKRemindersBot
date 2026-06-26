"""Relative day parser helpers: today/tomorrow/послезавтра and vague standalone times."""
from time_utils import BOT_TZ, ensure_aware

from datetime import datetime, timedelta
from typing import Optional, Tuple

from parser_time_tokens import VAGUE_TIME_WORDS, _extract_time_from_tokens


TZ = BOT_TZ
SYSTEM_DEFAULT_REMINDER_HOUR = 10
SYSTEM_DEFAULT_REMINDER_MINUTE = 0


def _default_time_or(value: Optional[Tuple[int, int]], fallback_hour: int, fallback_minute: int) -> Tuple[int, int]:
    return value if value is not None else (fallback_hour, fallback_minute)


def _parse_today_tomorrow(expr: str, now: datetime, default_time: Optional[Tuple[int, int]] = None) -> Optional[datetime]:
    s = expr.lower().strip()
    # today / сегодня
    for key, days in (("today", 0), ("сегодня", 0)):
        if s.startswith(key):
            rest = s[len(key):].strip()
            tokens = rest.split() if rest else []
            tokens, hour, minute = _extract_time_from_tokens(tokens, *_default_time_or(default_time, SYSTEM_DEFAULT_REMINDER_HOUR, SYSTEM_DEFAULT_REMINDER_MINUTE))
            base = ensure_aware(now).astimezone(TZ).date() + timedelta(days=days)
            return datetime(base.year, base.month, base.day, hour, minute, tzinfo=TZ)
    # tomorrow / завтра
    for key, days in (("tomorrow", 1), ("завтра", 1)):
        if s.startswith(key):
            rest = s[len(key):].strip()
            tokens = rest.split() if rest else []
            tokens, hour, minute = _extract_time_from_tokens(tokens, *_default_time_or(default_time, SYSTEM_DEFAULT_REMINDER_HOUR, SYSTEM_DEFAULT_REMINDER_MINUTE))
            base = ensure_aware(now).astimezone(TZ).date() + timedelta(days=days)
            return datetime(base.year, base.month, base.day, hour, minute, tzinfo=TZ)
    # day after tomorrow / послезавтра
    if s.startswith("day after tomorrow"):
        rest = s[len("day after tomorrow"):].strip()
        tokens = rest.split() if rest else []
        tokens, hour, minute = _extract_time_from_tokens(tokens, *_default_time_or(default_time, SYSTEM_DEFAULT_REMINDER_HOUR, SYSTEM_DEFAULT_REMINDER_MINUTE))
        base = ensure_aware(now).astimezone(TZ).date() + timedelta(days=2)
        return datetime(base.year, base.month, base.day, hour, minute, tzinfo=TZ)
    if s.startswith("послезавтра"):
        rest = s[len("послезавтра"):].strip()
        tokens = rest.split() if rest else []
        tokens, hour, minute = _extract_time_from_tokens(tokens, *_default_time_or(default_time, SYSTEM_DEFAULT_REMINDER_HOUR, SYSTEM_DEFAULT_REMINDER_MINUTE))
        base = ensure_aware(now).astimezone(TZ).date() + timedelta(days=2)
        return datetime(base.year, base.month, base.day, hour, minute, tzinfo=TZ)
    return None


def _parse_standalone_vague_time(expr: str, now: datetime) -> Optional[datetime]:
    s = expr.lower().strip()
    if s not in VAGUE_TIME_WORDS:
        return None

    hour, minute = VAGUE_TIME_WORDS[s]
    now_local = ensure_aware(now).astimezone(TZ)
    target_date = now_local.date()

    if (now_local.hour, now_local.minute) >= (hour, minute):
        target_date += timedelta(days=1)

    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=TZ,
    )
