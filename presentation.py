"""Pure presentation/formatting helpers for reminder UI."""

from datetime import datetime
from typing import Any, Dict, Optional


def format_recurring_human(pattern_type: Optional[str], payload: Optional[Dict[str, Any]]) -> str:
    """
    Делает человекочитаемое описание регулярности для списка /list.
    pattern_type: daily / weekly / weekly_multi / monthly / yearly
    payload: {"weekday": 0} / {"days":[...]} / {"day":15} / {"month":12,"day":25}
    """
    if not pattern_type:
        return "повтор"

    payload = payload or {}

    weekday_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    month_short = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    if pattern_type == "daily":
        return "daily"

    if pattern_type == "weekly":
        wd = int(payload.get("weekday", 0))
        wd = max(0, min(6, wd))
        return f"weekly ({weekday_short[wd]})"

    if pattern_type == "weekly_multi":
        days = payload.get("days") or []
        days = sorted(set(int(x) for x in days))
        if days == [0, 1, 2, 3, 4]:
            return "weekdays"
        if days == [5, 6]:
            return "weekends"
        nice = ", ".join(weekday_short[max(0, min(6, d))] for d in days) if days else "weekly"
        return f"weekly ({nice})"

    if pattern_type == "monthly":
        day = int(payload.get("day", 1))
        return f"monthly (day {day})"

    if pattern_type == "yearly":
        m = int(payload.get("month", 1))
        d = int(payload.get("day", 1))
        m = max(1, min(12, m))
        return f"yearly ({month_short[m - 1]} {d})"

    if pattern_type == "interval":
        value = int(payload.get("value", 0))
        unit = str(payload.get("unit", "")).lower()

        if unit == "minutes":
            return f"every {value} minute{'s' if value != 1 else ''}"
        if unit == "hours":
            return f"every {value} hour{'s' if value != 1 else ''}"
        if unit == "days":
            return f"every {value} day{'s' if value != 1 else ''}"
        if unit == "weeks":
            return f"every {value} week{'s' if value != 1 else ''}"
        if unit == "months":
            return f"every {value} month{'s' if value != 1 else ''}"

        return f"every {value} {unit}".strip()

    return pattern_type

def format_deleted_human(remind_at_iso: str, text: str, tpl_pattern_type: Optional[str], tpl_payload: Optional[Dict[str, Any]]) -> str:
    dt = datetime.fromisoformat(remind_at_iso)
    ts = dt.strftime("%d.%m %H:%M")

    suffix = ""
    if tpl_pattern_type:
        human = format_recurring_human(tpl_pattern_type, tpl_payload or {})
        suffix = f"  🔁 {human}" if human else "  🔁"

    return f"{ts} - {text}{suffix}"

# ===== Парсинг alias =====
