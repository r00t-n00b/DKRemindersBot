from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import main
from dkreminders_bot.parsing.parser_month_name_date import _parse_month_name_date


TZ = ZoneInfo("Europe/Madrid")


def test_parse_month_name_date_english_month_day():
    now = datetime(2026, 1, 1, 8, 0, tzinfo=TZ)

    assert _parse_month_name_date("january 25 20:30", now) == datetime(2026, 1, 25, 20, 30, tzinfo=TZ)


def test_parse_month_name_date_english_day_month_with_on_and_at():
    now = datetime(2026, 1, 1, 8, 0, tzinfo=TZ)

    assert _parse_month_name_date("on 25 january at 20:30", now) == datetime(2026, 1, 25, 20, 30, tzinfo=TZ)


def test_parse_month_name_date_russian_day_month_with_v():
    now = datetime(2026, 1, 1, 8, 0, tzinfo=TZ)

    assert _parse_month_name_date("1 октября в 12:30", now) == datetime(2026, 10, 1, 12, 30, tzinfo=TZ)


def test_parse_month_name_date_uses_default_time():
    now = datetime(2026, 1, 1, 8, 0, tzinfo=TZ)

    assert _parse_month_name_date("march 14", now, default_time=(11, 15)) == datetime(2026, 3, 14, 11, 15, tzinfo=TZ)


def test_parse_month_name_date_rolls_past_date_to_next_year():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_month_name_date("march 14 10:00", now) == datetime(2027, 3, 14, 10, 0, tzinfo=TZ)


def test_parse_month_name_date_rejects_unknown_expr():
    now = datetime(2026, 1, 1, 8, 0, tzinfo=TZ)

    assert _parse_month_name_date("tomorrow 10:00", now) is None


def test_parse_month_name_date_rejects_invalid_day():
    now = datetime(2026, 1, 1, 8, 0, tzinfo=TZ)

    with pytest.raises(ValueError):
        _parse_month_name_date("january 32 10:00", now)


def test_main_reexports_month_name_date_for_existing_callers():
    assert main._parse_month_name_date is _parse_month_name_date
