from datetime import datetime
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Europe/Madrid")


def test_no_dash_month_name_date_splits_and_parses(main_module):
    m = main_module
    now = datetime(2026, 2, 24, 20, 0, tzinfo=TZ)

    remind_at, text = m.parse_date_time_smart("on March 14 отменить принтер HP если решился", now)

    assert remind_at.year == 2026
    assert remind_at.month == 3
    assert remind_at.day == 14
    # default time in parser = 10:00 (если время не задано)
    assert remind_at.hour == 10
    assert remind_at.minute == 0
    assert text == "отменить принтер HP если решился"