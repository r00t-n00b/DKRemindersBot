"""Explicit recurrence modes and completion-relative interval calculation."""

import calendar
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo


def is_completion_based(pattern_type, payload):
    return pattern_type == "interval" and (payload or {}).get("recurrence_mode") == "completion"


def next_after_completion(payload, completed_at, timezone_name=None):
    """Measure elapsed intervals in UTC; months use the series' local calendar."""
    if completed_at.tzinfo is None:
        raise ValueError("Completion time must be timezone-aware")
    value = int(payload["value"])
    unit = payload["unit"]
    if value <= 0:
        raise ValueError("Interval must be positive")
    zone = ZoneInfo(timezone_name) if timezone_name else completed_at.tzinfo
    if unit in {"minutes", "hours", "days", "weeks"}:
        return (completed_at.astimezone(timezone.utc) + timedelta(**{unit: value})).astimezone(zone)
    if unit == "months":
        local = completed_at.astimezone(zone)
        index = local.year * 12 + local.month - 1 + value
        year, month = divmod(index, 12)
        month += 1
        return local.replace(year=year, month=month, day=min(local.day, calendar.monthrange(year, month)[1]))
    raise ValueError("Unknown interval unit")
