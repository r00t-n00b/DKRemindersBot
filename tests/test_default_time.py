import pytest

import main
from dkreminders_bot.settings.default_time import (
    _default_time_or,
    format_default_time_value,
    parse_default_time_value,
)


def test_parse_default_time_value_accepts_colon_and_dot_formats():
    assert parse_default_time_value("09:30") == (9, 30)
    assert parse_default_time_value("9:30") == (9, 30)
    assert parse_default_time_value("09.30") == (9, 30)
    assert parse_default_time_value(" 23:59 ") == (23, 59)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "9",
        "09",
        "09:3",
        "24:00",
        "12:60",
        "-1:00",
        "abc",
    ],
)
def test_parse_default_time_value_rejects_invalid_values(raw):
    with pytest.raises(ValueError, match="bad time"):
        parse_default_time_value(raw)


def test_format_default_time_value_zero_pads_values():
    assert format_default_time_value(9, 5) == "09:05"
    assert format_default_time_value(23, 59) == "23:59"


def test_default_time_or_uses_fallback_or_user_value():
    assert _default_time_or(None, 10, 0) == (10, 0)
    assert _default_time_or((9, 30), 10, 0) == (9, 30)
    assert _default_time_or(("9", "30"), 10, 0) == (9, 30)


def test_main_reexports_default_time_helpers_for_existing_callers():
    assert main.parse_default_time_value is parse_default_time_value
    assert main.format_default_time_value is format_default_time_value
    assert main._default_time_or is _default_time_or


def test_default_time_helpers_are_no_longer_defined_in_main_source():
    from pathlib import Path

    source = Path("main.py").read_text()

    assert "def parse_default_time_value(" not in source
    assert "def format_default_time_value(" not in source
    assert "def _default_time_or(" not in source
    assert "from dkreminders_bot.settings.default_time import" in source
