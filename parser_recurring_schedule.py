"""Recurring schedule calculation helpers."""
from time_utils import BOT_TZ, ensure_aware

import calendar
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


TZ = BOT_TZ


def _add_months_clamped(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])

    return dt.replace(year=year, month=month, day=day)


def compute_next_occurrence(
    pattern_type: str,
    payload: Dict[str, Any],
    time_hour: int,
    time_minute: int,
    after_dt: datetime,
) -> Optional[datetime]:
    local = ensure_aware(after_dt).astimezone(TZ)
    if pattern_type == "daily":
        candidate = local.replace(
            hour=time_hour,
            minute=time_minute,
            second=0,
            microsecond=0,
        )
        if candidate <= after_dt:
            candidate = candidate + timedelta(days=1)
        return candidate

    if pattern_type == "weekly":
        weekday = int(payload["weekday"])
        base_date = local.date()
        cur_wd = base_date.weekday()
        delta = (weekday - cur_wd + 7) % 7
        if delta == 0:
            candidate = datetime(
                base_date.year,
                base_date.month,
                base_date.day,
                time_hour,
                time_minute,
                tzinfo=TZ,
            )
            if candidate <= after_dt:
                delta = 7
        if delta != 0:
            base_date = base_date + timedelta(days=delta)
        return datetime(
            base_date.year,
            base_date.month,
            base_date.day,
            time_hour,
            time_minute,
            tzinfo=TZ,
        )

    if pattern_type == "weekly_multi":
        days = set(int(x) for x in payload.get("days", []))
        if not days:
            return None
        for delta in range(0, 8):
            d = local.date() + timedelta(days=delta)
            if d.weekday() in days:
                candidate = datetime(d.year, d.month, d.day, time_hour, time_minute, tzinfo=TZ)
                if candidate > after_dt:
                    return candidate
        return None

    if pattern_type == "monthly":
        day = int(payload["day"])
        base = local + timedelta(minutes=1)
        year = base.year
        month = base.month

        for _ in range(24):
            last_day = calendar.monthrange(year, month)[1]
            candidate_day = min(day, last_day)
            candidate = datetime(year, month, candidate_day, time_hour, time_minute, tzinfo=TZ)

            if candidate <= after_dt:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                continue

            return candidate

        return None

    if pattern_type == "yearly":
        month = int(payload["month"])
        day = int(payload["day"])

        base = ensure_aware(after_dt).astimezone(TZ)
        year = base.year

        # Если дата в этом году уже прошла - берем следующий год.
        # Плюс поддержка 29 февраля: ищем следующий валидный год.
        for _ in range(0, 12):
            try:
                candidate = datetime(year, month, day, time_hour, time_minute, tzinfo=TZ)
            except ValueError:
                year += 1
                continue

            if candidate <= after_dt:
                year += 1
                continue

            return candidate

        return None

    if pattern_type == "interval":
        value = int(payload.get("value", 0))
        unit = str(payload.get("unit", "")).lower()

        if value <= 0:
            return None

        base = ensure_aware(after_dt).astimezone(TZ).replace(second=0, microsecond=0)

        if unit == "minutes":
            return base + timedelta(minutes=value)

        if unit == "hours":
            return base + timedelta(hours=value)

        if unit == "days":
            candidate = base + timedelta(days=value)
            return candidate.replace(hour=time_hour, minute=time_minute, second=0, microsecond=0)

        if unit == "weeks":
            candidate = base + timedelta(weeks=value)
            return candidate.replace(hour=time_hour, minute=time_minute, second=0, microsecond=0)

        if unit == "months":
            candidate = _add_months_clamped(base, value)
            return candidate.replace(hour=time_hour, minute=time_minute, second=0, microsecond=0)

        return None

    return None
