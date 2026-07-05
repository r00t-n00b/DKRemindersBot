"""Time calculation helper for self-remind quick options."""

from datetime import datetime, timedelta

from dkreminders_bot.utils.time_utils import BOT_TZ, ensure_aware


TZ = BOT_TZ


def compute_self_remind_time(option: str, now: datetime) -> datetime:
    now = ensure_aware(now).astimezone(TZ)

    if option == "20m":
        return now + timedelta(minutes=20)

    if option == "1h":
        return now + timedelta(hours=1)

    if option == "3h":
        return now + timedelta(hours=3)

    if option == "tomorrow11":
        tomorrow = (now + timedelta(days=1)).date()
        return datetime(
            tomorrow.year,
            tomorrow.month,
            tomorrow.day,
            10,
            0,
            tzinfo=TZ,
        )

    if option == "nextmon":
        base = now.date()
        cur_wd = base.weekday()
        delta = (0 - cur_wd + 7) % 7
        if delta == 0:
            delta = 7
        target = base + timedelta(days=delta)
        return datetime(
            target.year,
            target.month,
            target.day,
            10,
            0,
            tzinfo=TZ,
        )

    raise ValueError(f"Unknown self reminder option: {option}")
