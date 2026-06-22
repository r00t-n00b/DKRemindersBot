from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("Europe/Madrid")


def test_parse_next_wednesday_ru_without_time(main_module):
    now = datetime(2026, 6, 3, 14, 41, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "в следующую среду - написать в цветы",
        now,
    )

    assert remind_at == datetime(2026, 6, 10, 10, 0, tzinfo=TZ)
    assert text == "написать в цветы"


def test_parse_in_one_week_ru_without_time(main_module):
    now = datetime(2026, 6, 3, 14, 41, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "через неделю - написать в цветы",
        now,
    )

    assert remind_at == datetime(2026, 6, 10, 14, 41, tzinfo=TZ)
    assert text == "написать в цветы"


def test_parse_next_week_ru_without_day(main_module):
    now = datetime(2026, 6, 8, 17, 12, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "на следующей неделе - сложить все деньги в общий аккаунт ббва",
        now,
    )

    assert remind_at == datetime(2026, 6, 15, 10, 0, tzinfo=TZ)
    assert text == "сложить все деньги в общий аккаунт ббва"


def test_parse_in_one_hour_ru(main_module):
    now = datetime(2026, 6, 8, 17, 12, tzinfo=TZ)

    remind_at, text = main_module.parse_date_time_smart(
        "через час - проверить духовку",
        now,
    )

    assert remind_at == datetime(2026, 6, 8, 18, 12, tzinfo=TZ)
    assert text == "проверить духовку"
