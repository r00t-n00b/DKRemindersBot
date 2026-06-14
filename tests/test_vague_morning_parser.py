from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


def test_standalone_morning_before_10_goes_to_today_10(main_module):
    now = datetime(2026, 6, 14, 2, 11, tzinfo=TZ)

    dt, text = main_module.parse_date_time_smart(
        "утром посмотреть https://untp.beer/69feadc35a",
        now,
    )

    assert dt == datetime(2026, 6, 14, 10, 0, tzinfo=TZ)
    assert text == "посмотреть https://untp.beer/69feadc35a"


def test_standalone_morning_after_10_goes_to_tomorrow_10(main_module):
    now = datetime(2026, 6, 14, 14, 11, tzinfo=TZ)

    dt, text = main_module.parse_date_time_smart(
        "утром посмотреть https://untp.beer/69feadc35a",
        now,
    )

    assert dt == datetime(2026, 6, 15, 10, 0, tzinfo=TZ)
    assert text == "посмотреть https://untp.beer/69feadc35a"


def test_tomorrow_morning_uses_tomorrow_10_and_removes_morning_from_text(main_module):
    now = datetime(2026, 6, 14, 14, 11, tzinfo=TZ)

    dt, text = main_module.parse_date_time_smart(
        "завтра утром посмотреть ссылку",
        now,
    )

    assert dt == datetime(2026, 6, 15, 10, 0, tzinfo=TZ)
    assert text == "посмотреть ссылку"


def test_standalone_evening_without_date_uses_same_vague_time_mechanism(main_module):
    now = datetime(2026, 6, 14, 14, 11, tzinfo=TZ)

    dt, text = main_module.parse_date_time_smart(
        "вечером купить молоко",
        now,
    )

    assert dt == datetime(2026, 6, 14, 18, 0, tzinfo=TZ)
    assert text == "купить молоко"


def test_standalone_evening_after_18_goes_to_tomorrow_18(main_module):
    now = datetime(2026, 6, 14, 19, 11, tzinfo=TZ)

    dt, text = main_module.parse_date_time_smart(
        "вечером купить молоко",
        now,
    )

    assert dt == datetime(2026, 6, 15, 18, 0, tzinfo=TZ)
    assert text == "купить молоко"
