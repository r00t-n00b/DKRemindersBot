"""Absolute date/time parser helpers."""
from dkreminders_bot.utils.time_utils import BOT_TZ, ensure_aware

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

from dkreminders_bot.parsing.parser_lexicon import MONTH_EN


TZ = BOT_TZ


def _default_time_or(value: Optional[Tuple[int, int]], fallback_hour: int, fallback_minute: int) -> Tuple[int, int]:
    return value if value is not None else (fallback_hour, fallback_minute)


def _parse_absolute(expr: str, now: datetime, default_time: Optional[Tuple[int, int]] = None) -> Optional[datetime]:
    s = expr.strip()
    local = ensure_aware(now).astimezone(TZ)

    # DD.MM.YYYY HH:MM / DD.MM.YY HH:MM
    m = re.fullmatch(
        r"(?P<day>\d{1,2})\.(?P<month>\d{1,2})\.(?P<year>\d{2,4})\s+(?P<hour>\d{1,2})[:.](?P<minute>\d{2})",
        s,
    )
    if m:
        day = int(m.group("day"))
        month = int(m.group("month"))
        year = int(m.group("year"))
        hour = int(m.group("hour"))
        minute = int(m.group("minute"))

        if year < 100:
            year += 2000

        try:
            return datetime(year, month, day, hour, minute, tzinfo=TZ)
        except ValueError as e:
            raise ValueError(f"Неверная дата или время: {e}") from e
    
    # DD.MM / DD.MM.YYYY без времени.
    # Важно: "23.10 - текст" = 23 октября, НЕ 23:10.
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?", s)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year_raw = m.group(3)

        year = local.year
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000

        try:
            dt = datetime(year, month, day, *_default_time_or(default_time, 10, 0), tzinfo=TZ)
        except ValueError as e:
            raise ValueError(f"Неверная дата или время: {e}") from e

        if dt < now - timedelta(minutes=1):
            try:
                dt = dt.replace(year=year + 1)
            except ValueError as e:
                raise ValueError(
                    f"Дата выглядит прошедшей и не может быть перенесена на следующий год: {e}"
                ) from e

        return dt


    # 25.01 [11:00] / 25/01 [11:00]
    m = re.fullmatch(
        r"(?P<day>\d{1,2})[./](?P<month>\d{1,2})(?:\s+(?P<hour>\d{1,2})[:.](?P<minute>\d{2}))?",
        s,
    )
    if m:
        day = int(m.group("day"))
        month = int(m.group("month"))
        if m.group("hour") is not None:
            hour = int(m.group("hour"))
            minute = int(m.group("minute"))
        else:
            hour, minute = _default_time_or(default_time, 10, 0)

        year = local.year
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
        except ValueError as e:
            raise ValueError(f"Неверная дата или время: {e}") from e

        if dt < now - timedelta(minutes=1):
            try:
                dt = dt.replace(year=year + 1)
            except ValueError as e:
                raise ValueError(
                    f"Дата выглядит прошедшей и не может быть перенесена на следующий год: {e}"
                ) from e
        return dt

    # только время: 23:59 или 23.59
    # Важно: проверяем ПОСЛЕ DD.MM, чтобы "23.10" стало датой,
    # а "23.59" дошло сюда, потому что месяца 59 не существует.
    m2 = re.fullmatch(r"(?P<hour>\d{1,2})[:.](?P<minute>\d{2})", s)
    if m2:
        hour = int(m2.group("hour"))
        minute = int(m2.group("minute"))

        # защита: "29.11" - это дата, а не время
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            dt = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if dt < now - timedelta(minutes=1):
                dt = dt + timedelta(days=1)
            return dt

    # 25 december [20:30]
    m_name_dm = re.fullmatch(
        r"(?P<day>\d{1,2})\s+(?P<month_name>[a-zA-Z]+)(?:\s+(?P<hour>\d{1,2})[:.](?P<minute>\d{2}))?$",
        s.lower().strip(),
    )
    if m_name_dm:
        day = int(m_name_dm.group("day"))
        month_name = m_name_dm.group("month_name")
        if month_name not in MONTH_EN:
            raise ValueError("Не знаю такой месяц")

        month = int(MONTH_EN[month_name])

        if m_name_dm.group("hour") is not None:
            hour = int(m_name_dm.group("hour"))
            minute = int(m_name_dm.group("minute"))
        else:
            hour, minute = _default_time_or(default_time, 10, 0)

        year = local.year
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
        except ValueError as e:
            raise ValueError(f"Неверная дата или время: {e}") from e

        if dt < now - timedelta(minutes=1):
            try:
                dt = dt.replace(year=year + 1)
            except ValueError as e:
                raise ValueError(
                    f"Дата выглядит прошедшей и не может быть перенесена на следующий год: {e}"
                ) from e

        return dt

    # january 25 [20:30]
    m_name_md = re.fullmatch(
        r"(?P<month_name>[a-zA-Z]+)\s+(?P<day>\d{1,2})(?:\s+(?P<hour>\d{1,2})[:.](?P<minute>\d{2}))?$",
        s.lower().strip(),
    )
    if m_name_md:
        month_name = m_name_md.group("month_name")
        if month_name not in MONTH_EN:
            raise ValueError("Не знаю такой месяц")

        month = int(MONTH_EN[month_name])
        day = int(m_name_md.group("day"))

        if m_name_md.group("hour") is not None:
            hour = int(m_name_md.group("hour"))
            minute = int(m_name_md.group("minute"))
        else:
            hour, minute = _default_time_or(default_time, 10, 0)

        year = local.year
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
        except ValueError as e:
            raise ValueError(f"Неверная дата или время: {e}") from e

        if dt < now - timedelta(minutes=1):
            try:
                dt = dt.replace(year=year + 1)
            except ValueError as e:
                raise ValueError(
                    f"Дата выглядит прошедшей и не может быть перенесена на следующий год: {e}"
                ) from e

        return dt

    return None
