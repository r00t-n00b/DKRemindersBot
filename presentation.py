"""Pure presentation/formatting helpers for reminder UI."""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

from keyboards import build_list_delete_keyboard



def _format_timezone_name(tz_name: Optional[str]) -> str:
    if not tz_name or tz_name == "Europe/Madrid":
        return "CET"
    if tz_name == "Europe/Moscow":
        return "Россия / Москва"
    return str(tz_name)


def _datetime_in_row_timezone(dt: datetime, tz_name: Optional[str]) -> datetime:
    if not tz_name:
        return dt
    try:
        return dt.astimezone(ZoneInfo(str(tz_name)))
    except Exception:
        return dt

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
        tz_name = _active_reminder_row_value(row, "timezone_name", 6)

        dt = _datetime_in_row_timezone(datetime.fromisoformat(remind_at_str), tz_name)
        tz_label = _format_timezone_name(tz_name)

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

        lines.append(f"{idx}. {ts} {tz_label} - {reminder_text}{suffix}")
        ids.append(rid)

    reply = header + "\n\n" + "\n".join(lines)
    keyboard_builder = list_delete_keyboard_builder or build_list_delete_keyboard
    return reply, ids, keyboard_builder(len(ids))


def format_empty_active_reminders_list_text(chat_alias: Optional[str] = None) -> str:
    empty_hint = "Напиши, например:\nнапомни завтра в 18:00 купить молоко"
    if chat_alias:
        return f"В чате '{chat_alias}' напоминаний нет.\n\n{empty_hint}"

    return f"Напоминаний нет.\n\n{empty_hint}"

def format_created_reminder_text(when_str: str, reminder_text: str) -> str:
    return f"Ок, напомню {when_str}: {reminder_text}"

def format_completed_reminder_text(base_text: str) -> str:
    return f"{base_text} (завершено ✅)"


def format_snoozed_reminder_text(reminder_text: str, when_str: str) -> str:
    return f"{reminder_text}\n\n(Отложено до {when_str})"


def format_snoozed_answer_text(when_str: str) -> str:
    return f"Отложено до {when_str}"


def format_deleted_snapshot_text(deleted_label: str, deleted_text: str) -> str:
    return f"{deleted_label}: {deleted_text}"


def format_restored_series_text(series_text: str, suffix: str, count: int) -> str:
    return f"Вернул серию: {series_text}{suffix} (инстансов: {count})"


def format_restored_single_text(restored_prefix: str, restored_text: str) -> str:
    return f"{restored_prefix}: {restored_text}"

def format_created_recurring_reminder_text(
    when_str: str,
    reminder_text: str,
    recurring_human: Optional[str],
    chat_alias: Optional[str] = None,
) -> str:
    freq_part = f"\nПовтор: {recurring_human}" if recurring_human else ""
    if chat_alias:
        return (
            f"Ок, создал повторяющееся напоминание в чате '{chat_alias}'.\n"
            f"Первое напоминание будет {when_str}: {reminder_text}"
            f"{freq_part}"
        )

    return (
        "Ок, создал повторяющееся напоминание.\n"
        f"Первое напоминание будет {when_str}: {reminder_text}"
        f"{freq_part}"
    )


def build_target_user_presentation_rows(rows, recurring_template_loader=None) -> List[Dict[str, Any]]:
    presentation_rows: List[Dict[str, Any]] = []

    for row in rows:
        if isinstance(row, dict):
            row_data = dict(row)
        elif hasattr(row, "keys"):
            row_data = dict(row)
        else:
            row_data = {
                "id": row[0],
                "text": row[1],
                "remind_at": row[2],
                "template_id": row[3] if len(row) > 3 else None,
            }

        tpl_id = row_data.get("template_id")
        if tpl_id is not None:
            tpl = recurring_template_loader(int(tpl_id)) if recurring_template_loader else None
            if tpl:
                row_data["pattern_type"] = tpl.get("pattern_type")
                row_data["payload"] = tpl.get("payload")
            else:
                row_data["pattern_type"] = row_data.get("pattern_type")
                row_data["payload"] = row_data.get("payload")

        presentation_rows.append(row_data)

    return presentation_rows

def build_target_user_reminders_list_response(
    rows,
    target_label: str,
    list_delete_keyboard_builder: Optional[Any] = None,
) -> Tuple[str, List[int], Optional[Any]]:
    lines: List[str] = []
    ids: List[int] = []

    for idx, row in enumerate(rows, start=1):
        rid = int(_active_reminder_row_value(row, "id", 0))
        reminder_text = str(_active_reminder_row_value(row, "text", 1) or "")
        remind_at_str = str(_active_reminder_row_value(row, "remind_at", 2) or "")
        template_id = _active_reminder_row_value(row, "template_id", 3)
        tpl_pattern_type = _active_reminder_row_value(row, "pattern_type", 4)
        tpl_payload_raw = _active_reminder_row_value(row, "payload", 5)
        tz_name = _active_reminder_row_value(row, "timezone_name", 6)

        dt = _datetime_in_row_timezone(datetime.fromisoformat(remind_at_str), tz_name)
        ts = dt.strftime("%d.%m %H:%M")
        tz_label = _format_timezone_name(tz_name)

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

        lines.append(f"{idx}. {ts} {tz_label} - {reminder_text}{suffix}")
        ids.append(rid)

    if not ids:
        return f"Ты не ставил напоминаний пользователю {target_label}.", [], None

    reply = (
        f"Напоминания, которые ты поставил пользователю {target_label}:\n\n"
        + "\n".join(lines)
    )

    keyboard_builder = list_delete_keyboard_builder or build_list_delete_keyboard
    return reply, ids, keyboard_builder(len(ids))

