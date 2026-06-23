"""Default reminder time parsing and formatting helpers."""

import re
from typing import Optional, Tuple


def parse_default_time_value(raw: str) -> Tuple[int, int]:
    s = (raw or "").strip().lower()
    s = s.replace(".", ":")

    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if not m:
        raise ValueError("bad time")

    hour = int(m.group(1))
    minute = int(m.group(2))

    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError("bad time")

    return hour, minute


def format_default_time_value(hour: int, minute: int) -> str:
    return f"{int(hour):02d}:{int(minute):02d}"


def _default_time_or(default_time: Optional[Tuple[int, int]], hour: int, minute: int) -> Tuple[int, int]:
    if default_time is None:
        return hour, minute
    return int(default_time[0]), int(default_time[1])
