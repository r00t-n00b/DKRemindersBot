"""Timezone-aware datetime helpers.

This module is intentionally tiny: it gives the rest of the bot one place
for "now", ISO serialization and ISO parsing rules.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

BOT_TZ = ZoneInfo("Europe/Madrid")


def aware_now(tz=BOT_TZ) -> datetime:
    return datetime.now(tz)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetime is not allowed")
    return dt.isoformat()


def from_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("naive datetime string is not allowed")
    return dt


def ensure_aware(dt: datetime, *, default_tz=BOT_TZ) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=default_tz)
    return dt
