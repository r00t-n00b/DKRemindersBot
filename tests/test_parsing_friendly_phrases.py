from datetime import datetime
from zoneinfo import ZoneInfo

def test_on_january_25_default_time(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart(
        "on January 25 - test",
        fixed_now,
    )
    assert text == "test"
    assert dt.strftime("%d.%m %H:%M") == "25.01 10:00"


def test_january_25_default_time(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart(
        "January 25 - test",
        fixed_now,
    )
    assert text == "test"
    assert dt.strftime("%d.%m %H:%M") == "25.01 10:00"


def test_on_25_january_default_time(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart(
        "on 25 January - test",
        fixed_now,
    )
    assert text == "test"
    assert dt.strftime("%d.%m %H:%M") == "25.01 10:00"


def test_on_25_01_with_time(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart(
        "on 25.01 11:00 - test",
        fixed_now,
    )
    assert text == "test"
    assert dt.strftime("%d.%m %H:%M") == "25.01 11:00"


def test_weekday_without_next_en(main_module, fixed_now):
    # fixed_now: 2025-11-28 (пятница)
    # ближайший четверг после пятницы - 04.12.2025
    dt, text = main_module.parse_date_time_smart(
        "Thursday 20:30 - test",
        fixed_now,
    )
    assert text == "test"
    assert dt.strftime("%d.%m %H:%M") == "04.12 20:30"


def test_weekday_without_next_ru(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart(
        "четверг 20:30 - test",
        fixed_now,
    )
    assert text == "test"
    assert dt.strftime("%d.%m %H:%M") == "04.12 20:30"


def test_v_chetverg_v_time_ru(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart(
        "в четверг в 20.30 - test",
        fixed_now,
    )
    assert text == "test"
    assert dt.strftime("%d.%m %H:%M") == "04.12 20:30"


def test_dot_in_time_is_supported(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart(
        "23.59 - hi",
        fixed_now,
    )
    assert text == "hi"
    assert dt.strftime("%d.%m %H:%M") == "28.11 23:59"


def test_date_with_dot_is_not_misread_as_time(main_module, fixed_now):
    # Регрессия: 29.11 не должен превращаться в "29:11" и валиться
    dt, text = main_module.parse_date_time_smart(
        "29.11 - hi",
        fixed_now,
    )
    assert text == "hi"
    assert dt.strftime("%d.%m %H:%M") == "29.11 10:00"


def test_on_25_december_at_2030(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart(
        "on 25 december at 20:30 - test",
        fixed_now,
    )
    assert text == "test"
    assert dt.strftime("%d.%m %H:%M") == "25.12 20:30"

def test_in_months_supported(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart("in 4 months - https://belgasonline.com/", fixed_now)
    assert text == "https://belgasonline.com/"
    assert dt == fixed_now.replace(year=2026, month=3, day=28, second=0, microsecond=0)

def test_in_years_supported(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart("in 1 year - hi", fixed_now)
    assert text == "hi"
    assert dt == fixed_now.replace(year=2026, second=0, microsecond=0)

def test_in_months_clamps_day(main_module):
    now = datetime(2025, 1, 31, 10, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    dt, text = main_module.parse_date_time_smart("in 1 month - hi", now)
    assert text == "hi"
    assert dt == now.replace(month=2, day=28, second=0, microsecond=0)
