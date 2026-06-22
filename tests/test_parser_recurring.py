from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import main
from parser_recurring import parse_recurring


TZ = ZoneInfo("Europe/Madrid")


def test_parse_recurring_weekly_english_weekday():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)  # Monday

    first_dt, text, pattern_type, payload, hour, minute = parse_recurring(
        "every monday 10:30 - standup",
        now,
    )

    assert first_dt == datetime(2026, 6, 22, 10, 30, tzinfo=TZ)
    assert text == "standup"
    assert pattern_type == "weekly"
    assert payload == {"weekday": 0}
    assert (hour, minute) == (10, 30)


def test_parse_recurring_interval_russian():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = parse_recurring(
        "каждые 3 дня - пить воду",
        now,
    )

    assert first_dt == datetime(2026, 6, 25, 10, 0, tzinfo=TZ)
    assert text == "пить воду"
    assert pattern_type == "interval"
    assert payload == {"value": 3, "unit": "days"}
    assert (hour, minute) == (10, 0)


def test_parse_recurring_monthly_ordinal_english():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = parse_recurring(
        "on the 15th of every month 12:00 - pay rent",
        now,
    )

    assert first_dt == datetime(2026, 7, 15, 12, 0, tzinfo=TZ)
    assert text == "pay rent"
    assert pattern_type == "monthly"
    assert payload == {"day": 15}
    assert (hour, minute) == (12, 0)


def test_parse_recurring_rejects_unknown_format():
    now = datetime(2026, 6, 22, 8, 0, tzinfo=TZ)

    with pytest.raises(ValueError):
        parse_recurring("tomorrow 10:00 - buy milk", now)


def test_main_reexports_parse_recurring_for_existing_callers():
    assert main.parse_recurring is parse_recurring
