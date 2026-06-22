"""Pure presentation/formatting helpers for reminder UI."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from keyboards import build_list_delete_keyboard


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


def _active_reminder_row_value(row: Any, key: str, index: int, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)

    try:
        return row[key]
    except (KeyError, TypeError):
        pass

    try:
        return row[index]
    except (IndexError, TypeError):
        return default


def build_active_reminders_list_response(rows, header: str, now_local: Optional[datetime] = None, list_delete_keyboard_builder: Optional[Any] = None) -> Tuple[str, List[int], Optional[Any]]:
    lines: List[str] = []
    ids: List[int] = []
    last_section: Optional[str] = None

    now_local = now_local or datetime.now().astimezone()
    today = now_local.date()
    tomorrow = today + timedelta(days=1)

    if not rows:
        return "Активных напоминаний нет.", [], None

    for idx, row in enumerate(rows, start=1):
        rid = int(_active_reminder_row_value(row, "id", 0))
        reminder_text = str(_active_reminder_row_value(row, "text", 1) or "")
        remind_at_str = str(_active_reminder_row_value(row, "remind_at", 2) or "")
        template_id = _active_reminder_row_value(row, "template_id", 3)
        tpl_pattern_type = _active_reminder_row_value(row, "pattern_type", 4)
        tpl_payload_raw = _active_reminder_row_value(row, "payload", 5)

        dt = datetime.fromisoformat(remind_at_str)

        if dt.date() == today:
            section = "Сегодня"
            ts = dt.strftime("%H:%M")
        elif dt.date() == tomorrow:
            section = "Завтра"
            ts = dt.strftime("%H:%M")
        else:
            section = "Позже"
            ts = dt.strftime("%d.%m %H:%M")

        if section != last_section:
            if lines:
                lines.append("")
            lines.append(section)
            last_section = section

        suffix = ""
        if template_id is not None:
            tpl_payload: Dict[str, Any] = {}
            if isinstance(tpl_payload_raw, dict):
                tpl_payload = tpl_payload_raw
            elif tpl_payload_raw:
                try:
                    tpl_payload = json.loads(tpl_payload_raw)
                except Exception:
                    tpl_payload = {}

            human = format_recurring_human(tpl_pattern_type, tpl_payload)
            suffix = f"  🔁 {human}" if human else "  🔁"

        lines.append(f"{idx}. {ts} - {reminder_text}{suffix}")
        ids.append(rid)

    reply = header + "\n\n" + "\n".join(lines)
    keyboard_builder = list_delete_keyboard_builder or build_list_delete_keyboard
    return reply, ids, keyboard_builder(len(ids))
