from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import main
from parser_date_time_smart import parse_date_time_smart


TZ = ZoneInfo("Europe/Madrid")


def test_parse_date_time_smart_dash_format():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    dt, text = parse_date_time_smart("tomorrow 10:30 - buy milk", now)

    assert dt == datetime(2026, 6, 23, 10, 30, tzinfo=TZ)
    assert text == "buy milk"


def test_parse_date_time_smart_moves_vague_time_from_text_to_expr():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    dt, text = parse_date_time_smart("завтра вечером купить молоко", now)

    assert dt == datetime(2026, 6, 23, 18, 0, tzinfo=TZ)
    assert text == "купить молоко"


def test_parse_date_time_smart_relative_in_expression():
    now = datetime(2026, 6, 22, 8, 0, 30, tzinfo=TZ)

    dt, text = parse_date_time_smart("in 5 minutes check", now)

    assert dt == datetime(2026, 6, 22, 8, 5, tzinfo=TZ)
    assert text == "check"


def test_parse_date_time_smart_absolute_without_dash():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    dt, text = parse_date_time_smart("25.12 20:30 buy gifts", now)

    assert dt == datetime(2026, 12, 25, 20, 30, tzinfo=TZ)
    assert text == "buy gifts"


def test_parse_date_time_smart_rejects_unparseable_text():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    with pytest.raises(ValueError):
        parse_date_time_smart("just random words", now)


def test_main_reexports_parse_date_time_smart_for_existing_callers():
    assert main.parse_date_time_smart is parse_date_time_smart
