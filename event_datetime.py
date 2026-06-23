"""Event-date parsing and event-before time helpers for self-remind flow."""

import re
from datetime import datetime, timedelta
from typing import Any, Optional, Tuple
from zoneinfo import ZoneInfo

from parser_lexicon import MONTH_EN


TZ = ZoneInfo("Europe/Madrid")


def _nearest_future_time_from_base(hour: int, minute: int, base_now: datetime) -> datetime:
    local = base_now.astimezone(TZ)
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local:
        candidate = candidate + timedelta(days=1)
    return candidate


def _parse_time_match(match: re.Match) -> Tuple[int, int]:
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError("Неверное время события")
    return hour, minute


def _build_event_datetime(year: int, month: int, day: int, hour: int, minute: int, base_now: datetime) -> datetime:
    local = base_now.astimezone(TZ)
    dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
    if dt <= local:
        try:
            dt = dt.replace(year=year + 1)
        except ValueError as e:
            raise ValueError(f"Неверная дата события: {e}") from e
    return dt


def extract_event_datetime_from_text(text: str, base_now: datetime) -> Optional[datetime]:
    """
    Best-effort парсер даты/времени события из текста reminder-а.

    Важно:
    - base_now = время прихода исходного reminder-а, а не время клика
    - не трогаем основной parse_date_time_smart
    """
    raw = (text or "").strip()
    if not raw:
        return None

    s = raw.lower()
    local = base_now.astimezone(TZ)

    time_re = r"(?P<hour>\d{1,2})[:.](?P<minute>\d{2})"

    relative_days = {
        "сегодня": 0,
        "today": 0,
        "завтра": 1,
        "tomorrow": 1,
        "послезавтра": 2,
        "day after tomorrow": 2,
    }

    # 1) Relative date где угодно + ближайшее время после нее:
    # "завтра футбол в 15:00", "football tomorrow at 15:00"
    for phrase, days in sorted(relative_days.items(), key=lambda x: -len(x[0])):
        m_date = re.search(rf"\b{re.escape(phrase)}\b", s)
        if not m_date:
            continue

        tail = s[m_date.end():]
        m_time = re.search(rf"(?:\bв\s+|\bat\s+)?{time_re}", tail)
        if not m_time:
            continue

        try:
            hour, minute = _parse_time_match(m_time)
        except ValueError:
            return None

        target_date = local.date() + timedelta(days=days)
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            tzinfo=TZ,
        )

    # 2) DD.MM / DD.MM.YYYY + время после даты, между ними могут быть слова:
    # "03.05 футбол в 15:00", "футбол 03.05 в 15:00"
    m = re.search(
        rf"(?P<day>\d{{1,2}})[./](?P<month>\d{{1,2}})(?:[./](?P<year>\d{{2,4}}))?"
        rf"(?P<middle>.{{0,80}}?)(?:\bв\s+|\bat\s+|\s+){time_re}",
        s,
    )
    if m:
        try:
            day = int(m.group("day"))
            month = int(m.group("month"))
            year_raw = m.group("year")
            if year_raw:
                year = int(year_raw)
                if year < 100:
                    year += 2000
            else:
                year = local.year

            hour, minute = _parse_time_match(m)
            return _build_event_datetime(year, month, day, hour, minute, base_now)
        except ValueError:
            return None

    # 3) Month name + day + время после даты:
    # "May 3 football at 15:00", "football on May 3 at 15:00"
    month_names = "|".join(sorted(MONTH_EN.keys(), key=len, reverse=True))
    m = re.search(
        rf"(?:\bon\s+)?(?P<month_name>{month_names})\s+(?P<day>\d{{1,2}})"
        rf"(?:\s+(?P<year>\d{{4}}))?"
        rf"(?P<middle>.{{0,80}}?)(?:\bв\s+|\bat\s+|\s+){time_re}",
        s,
    )
    if m:
        try:
            month = int(MONTH_EN[m.group("month_name")])
            day = int(m.group("day"))
            year = int(m.group("year")) if m.group("year") else local.year
            hour, minute = _parse_time_match(m)
            return _build_event_datetime(year, month, day, hour, minute, base_now)
        except ValueError:
            return None

    # 4) Day + month name + время после даты:
    # "3 May football at 15:00", "football on 3 May at 15:00"
    m = re.search(
        rf"(?:\bon\s+)?(?P<day>\d{{1,2}})\s+(?P<month_name>{month_names})"
        rf"(?:\s+(?P<year>\d{{4}}))?"
        rf"(?P<middle>.{{0,80}}?)(?:\bв\s+|\bat\s+|\s+){time_re}",
        s,
    )
    if m:
        try:
            month = int(MONTH_EN[m.group("month_name")])
            day = int(m.group("day"))
            year = int(m.group("year")) if m.group("year") else local.year
            hour, minute = _parse_time_match(m)
            return _build_event_datetime(year, month, day, hour, minute, base_now)
        except ValueError:
            return None

    # 5) Только время с явным предлогом:
    # "футбол в 15:00", "football at 15:00"
    m = re.search(rf"(?:\bв\s+|\bat\s+){time_re}", s)
    if m:
        try:
            hour, minute = _parse_time_match(m)
        except ValueError:
            return None
        return _nearest_future_time_from_base(hour, minute, base_now)

    return None


def normalize_relative_event_date_in_text(text: str, event_at: datetime) -> str:
    """
    Для event-based self-remind заменяем относительные даты на абсолютные,
    чтобы личный reminder не говорил "завтра", когда событие уже сегодня.

    Меняем только первое вхождение.
    """
    event_date = event_at.astimezone(TZ).strftime("%d.%m")

    replacements = [
        r"\bday after tomorrow\b",
        r"\btomorrow\b",
        r"\btoday\b",
        r"\bпослезавтра\b",
        r"\bзавтра\b",
        r"\bсегодня\b",
    ]

    result = text
    for pattern in replacements:
        result, count = re.subn(
            pattern,
            event_date,
            result,
            count=1,
            flags=re.IGNORECASE,
        )
        if count:
            return result

    return result


def get_self_remind_event_base(src: Any) -> datetime:
    return src.sent_at or src.remind_at


def compute_event_before_time(option: str, event_at: datetime) -> Optional[datetime]:
    if option == "20m":
        return event_at - timedelta(minutes=20)
    if option == "1h":
        return event_at - timedelta(hours=1)
    if option == "3h":
        return event_at - timedelta(hours=3)
    if option == "10h":
        return event_at - timedelta(hours=10)
    if option == "1d":
        return event_at - timedelta(days=1)
    return None
