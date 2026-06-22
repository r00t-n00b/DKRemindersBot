from datetime import datetime
from zoneinfo import ZoneInfo

import main
from parser_next_expression import _parse_next_expression


TZ = ZoneInfo("Europe/Madrid")


def test_parse_next_expression_weekday_without_prefix_today_future_time():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)  # Monday

    assert _parse_next_expression("monday 10:00", now) == datetime(2026, 6, 22, 10, 0, tzinfo=TZ)


def test_parse_next_expression_weekday_without_prefix_rolls_if_time_passed():
    now = datetime(2026, 6, 22, 11, 0, tzinfo=TZ)  # Monday

    assert _parse_next_expression("monday 10:00", now) == datetime(2026, 6, 29, 10, 0, tzinfo=TZ)


def test_parse_next_expression_next_weekday_is_strictly_next_week():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)  # Monday

    assert _parse_next_expression("next monday 10:00", now) == datetime(2026, 6, 29, 10, 0, tzinfo=TZ)


def test_parse_next_expression_russian_weekday_with_preposition():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)  # Monday

    assert _parse_next_expression("в среду 10:00", now) == datetime(2026, 6, 24, 10, 0, tzinfo=TZ)


def test_parse_next_expression_next_week_defaults_to_next_monday():
    now = datetime(2026, 6, 24, 8, 0, tzinfo=TZ)  # Wednesday

    assert _parse_next_expression("next week 10:00", now) == datetime(2026, 6, 29, 10, 0, tzinfo=TZ)


def test_parse_next_expression_next_month_clamps_day():
    now = datetime(2026, 1, 31, 8, 0, tzinfo=TZ)

    assert _parse_next_expression("next month 10:00", now) == datetime(2026, 2, 28, 10, 0, tzinfo=TZ)


def test_parse_next_expression_rejects_unknown_expr():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    assert _parse_next_expression("some random text", now) is None


def test_main_reexports_next_expression_for_existing_callers():
    assert main._parse_next_expression is _parse_next_expression
