"""Small helpers for parsing callback_data payloads."""


def parse_optional_int_callback_id(data: str, *, prefix: str):
    if not data.startswith(prefix):
        raise ValueError(f"callback data must start with {prefix!r}")

    raw_id = data[len(prefix):]
    try:
        return int(raw_id)
    except ValueError:
        return None


def parse_required_int_callback_id(data: str, *, prefix: str) -> int:
    if not data.startswith(prefix):
        raise ValueError(f"callback data must start with {prefix!r}")

    raw_id = data[len(prefix):]
    return int(raw_id)

def parse_snooze_action_callback_data(data: str):
    if not data.startswith("snooze:"):
        raise ValueError("callback data must start with 'snooze:'")

    _, raw_id, action = data.split(":", 2)
    return int(raw_id), action

def parse_snooze_calendar_callback_data(data: str):
    if not data.startswith("snooze_cal:"):
        raise ValueError("callback data must start with 'snooze_cal:'")

    _, raw_id, ym = data.split(":", 2)
    year_str, month_str = ym.split("-", 1)
    return int(raw_id), int(year_str), int(month_str)

def parse_snooze_pickdate_callback_data(data: str):
    if not data.startswith("snooze_pickdate:"):
        raise ValueError("callback data must start with 'snooze_pickdate:'")

    _, raw_id, date_str = data.split(":", 2)
    return int(raw_id), date_str

def parse_snooze_picktime_callback_data(data: str):
    if not data.startswith("snooze_picktime:"):
        raise ValueError("callback data must start with 'snooze_picktime:'")

    _, raw_id, date_str, time_str = data.split(":", 3)
    return int(raw_id), date_str, time_str

