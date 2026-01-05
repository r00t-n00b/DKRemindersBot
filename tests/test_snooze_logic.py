from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


def calc_snooze(now: datetime, action: str) -> datetime:
    # Это тестовая "спецификация". Логика должна совпадать с кодом в snooze_callback.
    if action == "20m":
        return now + timedelta(minutes=20)
    if action == "1h":
        return now + timedelta(hours=1)
    if action == "3h":
        return now + timedelta(hours=3)
    if action == "tomorrow":
        base = (now + timedelta(days=1)).astimezone(TZ).date()
        return datetime(base.year, base.month, base.day, 11, 0, tzinfo=TZ)
    if action == "nextmon":
        base = now.astimezone(TZ).date()
        cur_wd = base.weekday()
        delta = (0 - cur_wd + 7) % 7
        if delta == 0:
            delta = 7
        target = base + timedelta(days=delta)
        return datetime(target.year, target.month, target.day, 11, 0, tzinfo=TZ)
    raise ValueError("unknown")


def test_snooze_relative():
    now = datetime(2025, 11, 28, 10, 0, tzinfo=TZ)
    assert calc_snooze(now, "20m") == datetime(2025, 11, 28, 10, 20, tzinfo=TZ)
    assert calc_snooze(now, "1h") == datetime(2025, 11, 28, 11, 0, tzinfo=TZ)
    assert calc_snooze(now, "3h") == datetime(2025, 11, 28, 13, 0, tzinfo=TZ)


def test_snooze_tomorrow_default_11():
    now = datetime(2025, 11, 28, 22, 0, tzinfo=TZ)
    dt = calc_snooze(now, "tomorrow")
    assert dt.strftime("%d.%m %H:%M") == "29.11 11:00"


def test_snooze_next_monday_default_11():
    # 28.11.2025 это пятница, next Monday = 01.12
    now = datetime(2025, 11, 28, 10, 0, tzinfo=TZ)
    dt = calc_snooze(now, "nextmon")
    assert dt.strftime("%d.%m %H:%M") == "01.12 11:00"