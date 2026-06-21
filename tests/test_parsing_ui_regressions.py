import re
from datetime import datetime


def test_private_alias_split_does_not_trigger_for_ru_preposition(main_module):
    """
    Регрессия: в личке "/remind в четверг ..." не должно восприниматься как alias 'в'
    """
    m = main_module

    alias, rest = m.maybe_split_alias_first_token("в четверг в 20.30 - t2")
    assert alias is None
    assert rest.startswith("в четверг")


def test_private_alias_split_does_not_trigger_for_leading_number(main_module):
    """
    Регрессия: в личке "/remind 25 January ..." не должно восприниматься как alias '25'
    """
    m = main_module

    alias, rest = m.maybe_split_alias_first_token("25 January 20:30 - t4")
    assert alias is None
    assert rest.startswith("25 January")


def test_parse_ru_thursday_dot_time(main_module, fixed_now):
    """
    Реальный кейс из интерфейса:
    /remind в четверг в 20.30 - t2
    """
    m = main_module

    dt, text = m.parse_date_time_smart("в четверг в 20.30 - t2", fixed_now)
    assert text == "t2"
    assert dt.strftime("%Y-%m-%d %H:%M") == "2025-12-04 20:30"


def test_parse_day_monthname_time(main_module, fixed_now):
    """
    Реальный кейс из интерфейса:
    /remind 25 January 20:30 - t4
    """
    m = main_module

    dt, text = m.parse_date_time_smart("25 January 20:30 - t4", fixed_now)
    assert text == "t4"
    # fixed_now = 2025-11-28, значит 25 Jan уже прошел в 2025, берем 2026
    assert dt.strftime("%Y-%m-%d %H:%M") == "2026-01-25 20:30"


def test_month_name_parser_returns_none_for_time_only(main_module, fixed_now):
    """
    Защита от крэша: month-name парсер не должен ломаться на "23:59".
    Он должен вернуть None и дать отработать _parse_absolute (time-only).
    """
    m = main_module

    dt, _ = m.parse_date_time_smart("23:59 - t", fixed_now)
    assert dt.strftime("%Y-%m-%d %H:%M") == "2025-11-28 23:59"


def test_dot_in_time_is_supported(main_module, fixed_now):
    """
    "23.59" как время должно работать.
    """
    m = main_module

    dt, _ = m.parse_date_time_smart("23.59 - hi", fixed_now)
    assert dt.strftime("%Y-%m-%d %H:%M") == "2025-11-28 23:59"


def test_date_with_dot_is_not_misread_as_time(main_module, fixed_now):
    """
    Регрессия: 29.11 не должен превращаться в 29:11.
    """
    m = main_module

    dt, text = m.parse_date_time_smart("29.11 - hi", fixed_now)
    assert text == "hi"
    assert dt.strftime("%Y-%m-%d %H:%M") == "2025-11-29 10:00"