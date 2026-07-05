from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import main
from dkreminders_bot.parsing.parser_absolute import _parse_absolute


TZ = ZoneInfo("Europe/Madrid")


def test_parse_absolute_full_date_time():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_absolute("25.12.2026 20:30", now) == datetime(2026, 12, 25, 20, 30, tzinfo=TZ)


def test_parse_absolute_short_year_full_date_time():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_absolute("25.12.26 20:30", now) == datetime(2026, 12, 25, 20, 30, tzinfo=TZ)


def test_parse_absolute_date_without_time_uses_default_time():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_absolute("25.12", now, default_time=(11, 15)) == datetime(2026, 12, 25, 11, 15, tzinfo=TZ)


def test_parse_absolute_date_without_time_rolls_past_date_to_next_year():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_absolute("01.06", now) == datetime(2027, 6, 1, 10, 0, tzinfo=TZ)


def test_parse_absolute_time_only_today_if_future():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_absolute("23:59", now) == datetime(2026, 6, 22, 23, 59, tzinfo=TZ)


def test_parse_absolute_time_only_tomorrow_if_past():
    now = datetime(2026, 6, 22, 23, 59, tzinfo=TZ)

    assert _parse_absolute("08:00", now) == datetime(2026, 6, 23, 8, 0, tzinfo=TZ)


def test_parse_absolute_english_day_month():
    now = datetime(2026, 1, 1, 8, 0, tzinfo=TZ)

    assert _parse_absolute("25 december 20:30", now) == datetime(2026, 12, 25, 20, 30, tzinfo=TZ)


def test_parse_absolute_english_month_day():
    now = datetime(2026, 1, 1, 8, 0, tzinfo=TZ)

    assert _parse_absolute("december 25 20:30", now) == datetime(2026, 12, 25, 20, 30, tzinfo=TZ)


def test_parse_absolute_rejects_unknown_expr():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_absolute("tomorrow 10:00", now) is None


def test_parse_absolute_rejects_invalid_date():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    with pytest.raises(ValueError):
        _parse_absolute("31.02 10:00", now)


def test_main_reexports_absolute_parser_for_existing_callers():
    assert main._parse_absolute is _parse_absolute
