from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


def test_compute_daily(main_module):
    after = datetime(2025, 11, 28, 10, 0, tzinfo=TZ)
    nxt = main_module.compute_next_occurrence("daily", {}, 10, 0, after)
    assert nxt.strftime("%d.%m %H:%M") == "29.11 10:00"


def test_compute_weekly(main_module):
    after = datetime(2025, 11, 28, 10, 0, tzinfo=TZ)  # пятница
    nxt = main_module.compute_next_occurrence("weekly", {"weekday": 0}, 10, 0, after)
    assert nxt.weekday() == 0
    assert nxt.strftime("%H:%M") == "10:00"


def test_compute_weekly_multi(main_module):
    after = datetime(2025, 11, 28, 10, 0, tzinfo=TZ)  # пятница
    nxt = main_module.compute_next_occurrence("weekly_multi", {"days": [5, 6]}, 11, 0, after)
    # ближайший день из [сб, вс] - суббота
    assert nxt.strftime("%d.%m %H:%M") == "29.11 11:00"


def test_compute_monthly(main_module):
    after = datetime(2025, 11, 28, 10, 0, tzinfo=TZ)
    nxt = main_module.compute_next_occurrence("monthly", {"day": 15}, 10, 0, after)
    assert nxt.strftime("%d.%m %H:%M") == "15.12 10:00"