"""Month-name date parser helpers."""

import re
from datetime import datetime
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from parser_lexicon import MONTH_EN, MONTH_RU


TZ = ZoneInfo("Europe/Madrid")


def _default_time_or(value: Optional[Tuple[int, int]], fallback_hour: int, fallback_minute: int) -> Tuple[int, int]:
    return value if value is not None else (fallback_hour, fallback_minute)


def _parse_month_name_date(expr: str, now: datetime, default_time: Optional[Tuple[int, int]] = None) -> Optional[datetime]:
    """
    Понимает:
    - on January 25
    - on January 25 at 20:30
    - January 25
    - January 25 at 20:30
    - on 25 January
    - on 25 January at 20:30
    """
    s = expr.lower().strip()
    local = now.astimezone(TZ)

    # Нормализация: убираем лишний "on" в начале
    if s.startswith("on "):
        s = s[3:].strip()

    tokens = s.split()
    if not tokens:
        return None

    # Вынесем время, если в конце "at HH:MM" или просто "HH:MM"
    # Примеры:
    #   january 25 at 20:30
    #   january 25 20:30
    hour, minute = _default_time_or(default_time, 10, 0)

    def _try_parse_time_token(tok: str) -> Optional[Tuple[int, int]]:
        m_time = re.fullmatch(r"(?P<h>\d{1,2})[:.](?P<m>\d{2})", tok)
        if not m_time:
            return None
        h = int(m_time.group("h"))
        m_ = int(m_time.group("m"))
        if not (0 <= h < 24 and 0 <= m_ < 60):
            return None
        return h, m_

    if len(tokens) >= 2 and tokens[-2] in {"at", "в"}:
        parsed = _try_parse_time_token(tokens[-1])
        if parsed is not None:
            hour, minute = parsed
            tokens = tokens[:-2]
    else:
        parsed = _try_parse_time_token(tokens[-1]) if tokens else None
        if parsed is not None:
            hour, minute = parsed
            tokens = tokens[:-1]

    # Если осталась не дата (а, например, было только "23:59") - это не наш формат
    if len(tokens) < 2:
        return None

    month_names = dict(MONTH_EN)
    month_names.update(MONTH_RU)

    # Вариант A: "<month> <day>"
    if tokens[0] in month_names and tokens[1].isdigit():
        month = int(month_names[tokens[0]])
        day = int(tokens[1])
    # Вариант B: "<day> <month>"
    elif tokens[1] in month_names and tokens[0].isdigit():
        day = int(tokens[0])
        month = int(month_names[tokens[1]])
    else:
        return None

    if not (1 <= day <= 31):
        raise ValueError("Неверный день месяца")

    year = local.year
    try:
        dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
    except ValueError as e:
        raise ValueError(f"Неверная дата или время: {e}") from e

    # Если дата уже прошла (с небольшим допуском) - переносим на следующий год
    if (month, day) < (local.month, local.day):
        dt = dt.replace(year=year + 1)
        try:
            dt = dt.replace(year=year + 1)
        except ValueError as e:
            raise ValueError(
                f"Дата выглядит прошедшей и не может быть перенесена на следующий год: {e}"
            ) from e

    return dt
