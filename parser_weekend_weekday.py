"""Weekend/weekday parser helpers."""

from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from parser_time_tokens import _extract_time_from_tokens


TZ = ZoneInfo("Europe/Madrid")
SYSTEM_DEFAULT_REMINDER_HOUR = 10
SYSTEM_DEFAULT_REMINDER_MINUTE = 0


def _default_time_or(value: Optional[Tuple[int, int]], fallback_hour: int, fallback_minute: int) -> Tuple[int, int]:
    return value if value is not None else (fallback_hour, fallback_minute)


def _parse_weekend_weekday(expr: str, now: datetime, default_time: Optional[Tuple[int, int]] = None) -> Optional[datetime]:
    s = expr.lower().strip()
    tokens = s.split()
    if not tokens:
        return None

    local = now.astimezone(TZ)

    tokens_no_time, hour, minute = _extract_time_from_tokens(tokens, *_default_time_or(default_time, SYSTEM_DEFAULT_REMINDER_HOUR, SYSTEM_DEFAULT_REMINDER_MINUTE))
    if not tokens_no_time:
        return None

    is_weekend = False
    is_weekday = False

    joined = " ".join(tokens_no_time)

    if "weekend" in joined or "выходн" in joined:
        is_weekend = True
    if "weekday" in joined or "workday" in joined or "будн" in joined or "рабоч" in joined:
        is_weekday = True

    if not (is_weekend or is_weekday):
        return None

    if is_weekend and is_weekday:
        return None

    if is_weekend:
        allowed = {5, 6}  # сб, вс
    else:
        allowed = {0, 1, 2, 3, 4}  # пн-пт

    for delta in range(0, 8):
        d = local.date() + timedelta(days=delta)
        if d.weekday() in allowed:
            candidate = datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ)
            if candidate > now:
                return candidate
    return None
