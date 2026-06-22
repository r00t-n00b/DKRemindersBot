from datetime import datetime
from zoneinfo import ZoneInfo

import main
from parser_relative_day import _parse_standalone_vague_time, _parse_today_tomorrow


TZ = ZoneInfo("Europe/Madrid")


def test_parse_today_tomorrow_today_with_explicit_time():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_today_tomorrow("today 9:30", now) == datetime(2026, 6, 22, 9, 30, tzinfo=TZ)


def test_parse_today_tomorrow_russian_tomorrow_default_time():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_today_tomorrow("завтра", now) == datetime(2026, 6, 23, 10, 0, tzinfo=TZ)


def test_parse_today_tomorrow_day_after_tomorrow_english():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_today_tomorrow("day after tomorrow 11:15", now) == datetime(2026, 6, 24, 11, 15, tzinfo=TZ)


def test_parse_today_tomorrow_rejects_unknown_expr():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_today_tomorrow("next week", now) is None


def test_parse_standalone_vague_time_today_if_future():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_standalone_vague_time("утром", now) == datetime(2026, 6, 22, 10, 0, tzinfo=TZ)


def test_parse_standalone_vague_time_tomorrow_if_past():
    now = datetime(2026, 6, 22, 11, 0, tzinfo=TZ)

    assert _parse_standalone_vague_time("утром", now) == datetime(2026, 6, 23, 10, 0, tzinfo=TZ)


def test_main_reexports_relative_day_helpers_for_existing_callers():
    assert main._parse_today_tomorrow is _parse_today_tomorrow
    assert main._parse_standalone_vague_time is _parse_standalone_vague_time
