from datetime import datetime
from zoneinfo import ZoneInfo

import main
from parser_weekend_weekday import _parse_weekend_weekday


TZ = ZoneInfo("Europe/Madrid")


def test_parse_weekend_weekday_weekend_from_weekday():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)  # Monday

    assert _parse_weekend_weekday("weekend 10:00", now) == datetime(2026, 6, 27, 10, 0, tzinfo=TZ)


def test_parse_weekend_weekday_weekday_rolls_past_today_to_next_workday():
    now = datetime(2026, 6, 22, 11, 0, tzinfo=TZ)  # Monday

    assert _parse_weekend_weekday("weekday 10:00", now) == datetime(2026, 6, 23, 10, 0, tzinfo=TZ)


def test_parse_weekend_weekday_russian_weekend_with_vague_time():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)  # Monday

    assert _parse_weekend_weekday("выходные утром", now) == datetime(2026, 6, 27, 10, 0, tzinfo=TZ)


def test_parse_weekend_weekday_rejects_weekend_and_weekday_together():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_weekend_weekday("weekend weekday 10:00", now) is None


def test_parse_weekend_weekday_rejects_unknown_expr():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_weekend_weekday("next monday 10:00", now) is None


def test_main_reexports_weekend_weekday_for_existing_callers():
    assert main._parse_weekend_weekday is _parse_weekend_weekday
