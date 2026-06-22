from datetime import datetime
from zoneinfo import ZoneInfo

import main
from parser_in_expression import _add_months, _parse_in_expression


TZ = ZoneInfo("Europe/Madrid")


def test_add_months_keeps_day_when_possible():
    dt = datetime(2026, 1, 15, 10, 0, tzinfo=TZ)

    assert _add_months(dt, 1) == datetime(2026, 2, 15, 10, 0, tzinfo=TZ)


def test_add_months_clamps_last_day():
    dt = datetime(2026, 1, 31, 10, 0, tzinfo=TZ)

    assert _add_months(dt, 1) == datetime(2026, 2, 28, 10, 0, tzinfo=TZ)


def test_parse_in_expression_english_minutes():
    now = datetime(2026, 6, 22, 10, 0, 30, tzinfo=TZ)

    assert _parse_in_expression(["in", "5", "minutes"], now) == datetime(2026, 6, 22, 10, 5, tzinfo=TZ)


def test_parse_in_expression_russian_implicit_hour():
    now = datetime(2026, 6, 22, 10, 0, 30, tzinfo=TZ)

    assert _parse_in_expression(["через", "час"], now) == datetime(2026, 6, 22, 11, 0, tzinfo=TZ)


def test_parse_in_expression_month_clamps_day():
    now = datetime(2026, 1, 31, 10, 0, 30, tzinfo=TZ)

    assert _parse_in_expression(["in", "1", "month"], now) == datetime(2026, 2, 28, 10, 0, tzinfo=TZ)


def test_parse_in_expression_rejects_unknown_prefix():
    now = datetime(2026, 6, 22, 10, 0, tzinfo=TZ)

    assert _parse_in_expression(["after", "5", "minutes"], now) is None


def test_main_reexports_in_expression_helpers_for_existing_callers():
    assert main._add_months is _add_months
    assert main._parse_in_expression is _parse_in_expression
