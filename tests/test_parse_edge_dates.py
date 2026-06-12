from datetime import datetime

import pytest
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Europe/Madrid")


def test_parse_non_leap_day_raises(main_module):
    now = datetime(2025, 1, 24, 10, 0, tzinfo=TZ)

    # 2025 is not a leap year
    with pytest.raises(ValueError):
        main_module.parse_date_time_smart("29.02 - hi", now)


def test_parse_leap_day_ok_in_leap_year(main_module):
    now = datetime(2024, 1, 24, 10, 0, tzinfo=TZ)

    dt, text = main_module.parse_date_time_smart("29.02 12:00 - hi", now)

    assert text == "hi"
    assert dt.year == 2024
    assert dt.month == 2
    assert dt.day == 29
    assert dt.hour == 12
    assert dt.minute == 0

def test_parse_absolute_with_year_and_time(main_module):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=TZ)

    dt, text = main_module.parse_date_time_smart(
        "5.02.2026 17:00 - test",
        now,
    )

    assert dt.year == 2026
    assert dt.month == 2
    assert dt.day == 5
    assert dt.hour == 17
    assert dt.minute == 0
    assert text == "test"