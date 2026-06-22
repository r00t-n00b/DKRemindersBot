"""Relative in/через expression parser helpers."""

import calendar
from datetime import datetime, timedelta
from typing import List, Optional


def _add_months(dt: datetime, months: int) -> datetime:
    # months может быть > 12, < 0 - все ок
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    d = min(dt.day, last_day)
    return dt.replace(year=y, month=m, day=d)


def _parse_in_expression(tokens: List[str], now: datetime) -> Optional[datetime]:
    if not tokens:
        return None
    first = tokens[0]
    if first not in {"in", "через"}:
        return None
    if len(tokens) < 2:
        return None

    if len(tokens) >= 3:
        try:
            amount = int(tokens[1])
        except ValueError:
            return None
        unit = tokens[2]
    elif first == "через":
        amount = 1
        unit = tokens[1]
    else:
        return None

    # английские варианты
    en_minutes = {"minute", "minutes", "min", "mins", "m"}
    en_hours = {"hour", "hours", "h", "hr", "hrs"}
    en_days = {"day", "days", "d"}
    en_weeks = {"week", "weeks", "w"}
    en_months = {"month", "months", "mon"}  # mon опционально
    en_years = {"year", "years", "yr", "yrs", "y"}

    # русские варианты
    ru_minutes = {"минуту", "минуты", "минут", "мин", "м"}
    ru_hours = {"час", "часа", "часов", "ч"}
    ru_days = {"день", "дня", "дней"}
    ru_weeks = {"неделю", "недели", "недель", "нед"}
    ru_months = {"месяц", "месяца", "месяцев", "мес"}
    ru_years = {"год", "года", "лет", "г"}

    # 1) фиксированные единицы
    delta: Optional[timedelta] = None
    if unit in en_minutes or unit in ru_minutes:
        delta = timedelta(minutes=amount)
    elif unit in en_hours or unit in ru_hours:
        delta = timedelta(hours=amount)
    elif unit in en_days or unit in ru_days:
        delta = timedelta(days=amount)
    elif unit in en_weeks or unit in ru_weeks:
        delta = timedelta(weeks=amount)

    if delta is not None:
        dt = now + delta
        return dt.replace(second=0, microsecond=0)

    # 2) months/years (календарная арифметика)
    if unit in en_months or unit in ru_months:
        dt = _add_months(now, amount)
        return dt.replace(second=0, microsecond=0)

    if unit in en_years or unit in ru_years:
        dt = _add_months(now, amount * 12)
        return dt.replace(second=0, microsecond=0)

    return None
