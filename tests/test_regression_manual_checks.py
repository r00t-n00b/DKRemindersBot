from datetime import datetime

def test_alias_split_does_not_eat_ru_v(main_module):
    """
    Регрессия: "/remind в четверг ..." в личке не должен воспринимать "в" как alias.
    """
    m = main_module
    alias, rest = m.maybe_split_alias_first_token("в четверг в 20.30 - t2")
    assert alias is None
    assert rest == "в четверг в 20.30 - t2"


def test_alias_split_does_not_eat_day_number(main_module):
    """
    Регрессия: "/remind 25 January ..." не должен воспринимать "25" как alias.
    """
    m = main_module
    alias, rest = m.maybe_split_alias_first_token("25 January 20:30 - t4")
    assert alias is None
    assert rest == "25 January 20:30 - t4"


def test_alias_split_does_not_eat_on(main_module):
    """
    Регрессия: "/remind on ..." не должен воспринимать "on" как alias.
    """
    m = main_module
    alias, rest = m.maybe_split_alias_first_token("on January 25 - test")
    assert alias is None
    assert rest == "on January 25 - test"


def test_alias_split_still_detects_real_alias(main_module):
    """
    Проверка: настоящий alias (например "Гарсия") по-прежнему вырезается как alias.
    """
    m = main_module
    alias, rest = m.maybe_split_alias_first_token("Гарсия 29.11 12:00 - alias-still-works")
    assert alias == "Гарсия"
    assert rest == "29.11 12:00 - alias-still-works"


def test_parse_ru_thursday_dot_time(main_module, fixed_now):
    """
    /remind в четверг в 20.30 - ...
    """
    m = main_module
    dt, text = m.parse_date_time_smart("в четверг в 20.30 - ru-thu-dot", fixed_now)
    assert text == "ru-thu-dot"
    assert dt.strftime("%d.%m %H:%M") == "04.12 20:30"


def test_parse_day_month_name(main_module, fixed_now):
    """
    /remind 25 January 20:30 - ...
    """
    m = main_module
    dt, text = m.parse_date_time_smart("25 January 20:30 - day-month", fixed_now)
    assert text == "day-month"
    assert dt.strftime("%d.%m.%Y %H:%M") == "25.01.2026 20:30"


def test_parse_on_month_day_default_time(main_module, fixed_now):
    """
    /remind on January 25 - ...
    (без времени должно быть 11:00)
    """
    m = main_module
    dt, text = m.parse_date_time_smart("on January 25 - on-month-day", fixed_now)
    assert text == "on-month-day"
    assert dt.strftime("%d.%m.%Y %H:%M") == "25.01.2026 11:00"


def test_parse_dot_time(main_module, fixed_now):
    """
    /remind 23.59 - ...
    """
    m = main_module
    dt, text = m.parse_date_time_smart("23.59 - time-dot", fixed_now)
    assert text == "time-dot"
    assert dt.strftime("%d.%m.%Y %H:%M") == "28.11.2025 23:59"


def test_parse_dot_date_default_time(main_module, fixed_now):
    """
    /remind 29.11 - ...
    (дата с точкой не должна ломаться и становиться 29:11)
    """
    m = main_module
    dt, text = m.parse_date_time_smart("29.11 - date-dot", fixed_now)
    assert text == "date-dot"
    assert dt.strftime("%d.%m.%Y %H:%M") == "29.11.2025 11:00"


def test_parse_on_weekday_at_time(main_module, fixed_now):
    """
    /remind on Thursday at 20:30 - ...
    """
    m = main_module
    dt, text = m.parse_date_time_smart("on Thursday at 20:30 - on-weekday-at", fixed_now)
    assert text == "on-weekday-at"
    assert dt.strftime("%d.%m %H:%M") == "04.12 20:30"