from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("Europe/Madrid")


def test_parse_day_english_month_without_time_defaults_to_11(main_module):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "25 december - buy presents",
        now,
    )

    assert remind_at == datetime(2026, 12, 25, 11, 0, tzinfo=TZ)
    assert text == "buy presents"


def test_parse_day_english_month_with_time(main_module):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "25 december 20:30 - buy presents",
        now,
    )

    assert remind_at == datetime(2026, 12, 25, 20, 30, tzinfo=TZ)
    assert text == "buy presents"


def test_parse_day_english_month_with_dot_time(main_module):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "25 december 20.30 - buy presents",
        now,
    )

    assert remind_at == datetime(2026, 12, 25, 20, 30, tzinfo=TZ)
    assert text == "buy presents"


def test_parse_day_english_month_rolls_past_date_to_next_year(main_module):
    now = datetime(2026, 12, 26, 10, 0, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "25 december - buy presents",
        now,
    )

    assert remind_at == datetime(2027, 12, 25, 11, 0, tzinfo=TZ)
    assert text == "buy presents"


def test_parse_day_unknown_english_month_raises(main_module):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    with pytest.raises(ValueError, match="Не знаю такой месяц"):
        main_module.parse_date_time_smart(
            "25 foober - impossible",
            now,
        )


def test_parse_day_english_month_invalid_date_raises(main_module):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    with pytest.raises(ValueError, match="Неверная дата или время"):
        main_module.parse_date_time_smart(
            "31 february - impossible",
            now,
        )


def test_parse_english_month_day_without_time_defaults_to_11(main_module):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "december 25 - buy presents",
        now,
    )

    assert remind_at == datetime(2026, 12, 25, 11, 0, tzinfo=TZ)
    assert text == "buy presents"


def test_parse_english_month_day_with_time(main_module):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "december 25 20:30 - buy presents",
        now,
    )

    assert remind_at == datetime(2026, 12, 25, 20, 30, tzinfo=TZ)
    assert text == "buy presents"


def test_parse_english_month_day_with_dot_time(main_module):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "december 25 20.30 - buy presents",
        now,
    )

    assert remind_at == datetime(2026, 12, 25, 20, 30, tzinfo=TZ)
    assert text == "buy presents"


def test_parse_english_month_day_rolls_past_date_to_next_year(main_module):
    now = datetime(2026, 12, 26, 10, 0, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "december 25 - buy presents",
        now,
    )

    assert remind_at == datetime(2027, 12, 25, 11, 0, tzinfo=TZ)
    assert text == "buy presents"


def test_parse_unknown_english_month_day_raises(main_module):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    with pytest.raises(ValueError, match="Не знаю такой месяц"):
        main_module.parse_date_time_smart(
            "foober 25 - impossible",
            now,
        )


def test_parse_english_month_day_invalid_date_raises(main_module):
    now = datetime(2026, 6, 12, 10, 0, tzinfo=TZ)

    with pytest.raises(ValueError, match="Неверная дата или время"):
        main_module.parse_date_time_smart(
            "february 31 - impossible",
            now,
        )
