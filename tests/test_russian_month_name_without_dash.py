from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


def test_russian_month_name_without_dash_defaults_to_10(main_module):
    now = datetime(2026, 6, 15, 13, 26, tzinfo=TZ)

    dt, text = main_module.parse_date_time_smart(
        "1 октября пересчитать стоимость начинки квартиры и поменять в страховке",
        now,
    )

    assert dt == datetime(2026, 10, 1, 10, 0, tzinfo=TZ)
    assert text == "пересчитать стоимость начинки квартиры и поменять в страховке"


def test_russian_month_name_without_dash_with_time(main_module):
    now = datetime(2026, 6, 15, 13, 26, tzinfo=TZ)

    dt, text = main_module.parse_date_time_smart(
        "1 октября 12:30 пересчитать страховку",
        now,
    )

    assert dt == datetime(2026, 10, 1, 12, 30, tzinfo=TZ)
    assert text == "пересчитать страховку"


def test_russian_month_name_without_dash_with_v_time(main_module):
    now = datetime(2026, 6, 15, 13, 26, tzinfo=TZ)

    dt, text = main_module.parse_date_time_smart(
        "1 октября в 12:30 пересчитать страховку",
        now,
    )

    assert dt == datetime(2026, 10, 1, 12, 30, tzinfo=TZ)
    assert text == "пересчитать страховку"


def test_russian_month_name_with_dash_does_not_keep_dash_in_text(main_module):
    now = datetime(2026, 6, 15, 13, 26, tzinfo=TZ)

    dt, text = main_module.parse_date_time_smart(
        "1 октября - пересчитать стоимость начинки квартиры и поменять в страховке",
        now,
    )

    assert dt == datetime(2026, 10, 1, 10, 0, tzinfo=TZ)
    assert text == "пересчитать стоимость начинки квартиры и поменять в страховке"


def test_russian_month_name_with_dash_and_time_does_not_keep_dash_in_text(main_module):
    now = datetime(2026, 6, 15, 13, 26, tzinfo=TZ)

    dt, text = main_module.parse_date_time_smart(
        "1 октября в 12:30 - пересчитать страховку",
        now,
    )

    assert dt == datetime(2026, 10, 1, 12, 30, tzinfo=TZ)
    assert text == "пересчитать страховку"
