from datetime import datetime
from zoneinfo import ZoneInfo
import pytest


def test_parse_date_time_smart_parses_ddmm_time_with_dash(main_module):
    m = main_module
    TZ = ZoneInfo("Europe/Madrid")
    now = datetime(2025, 1, 24, 1, 0, tzinfo=TZ)

    dt, text = m.parse_date_time_smart("02.02 12:00 - завтра футбол", now)

    assert dt.year == 2025
    assert dt.month == 2
    assert dt.day == 2
    assert dt.hour == 12
    assert dt.minute == 0
    assert text == "завтра футбол"