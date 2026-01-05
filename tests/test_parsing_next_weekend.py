def test_next_week(main_module, fixed_now):
    dt, _ = main_module.parse_date_time_smart("next week - t", fixed_now)
    # next week = понедельник следующей недели 11:00 по умолчанию
    assert dt.strftime("%d.%m %H:%M") == "01.12 11:00"


def test_next_month(main_module, fixed_now):
    dt, _ = main_module.parse_date_time_smart("next month - t", fixed_now)
    # 28.11 -> 28.12 (если такой день есть) 11:00
    assert dt.strftime("%d.%m %H:%M") == "28.12 11:00"


def test_next_weekday_name(main_module, fixed_now):
    dt, _ = main_module.parse_date_time_smart("next Monday 10:00 - t", fixed_now)
    assert dt.strftime("%d.%m %H:%M") == "01.12 10:00"

    dt2, _ = main_module.parse_date_time_smart("следующий понедельник 10:00 - t", fixed_now)
    assert dt2.strftime("%d.%m %H:%M") == "01.12 10:00"


def test_weekend_weekday_workday(main_module, fixed_now):
    # fixed_now пятница 28.11, ближайшие выходные - 29.11
    dt, _ = main_module.parse_date_time_smart("weekend - t", fixed_now)
    assert dt.strftime("%d.%m %H:%M") == "29.11 11:00"

    dt2, _ = main_module.parse_date_time_smart("weekday 09:00 - t", fixed_now)
    # ближайший будний день с 09:00 - это понедельник 01.12 09:00 (пт 28.11 уже 10:00)
    assert dt2.strftime("%d.%m %H:%M") == "01.12 09:00"

    dt3, _ = main_module.parse_date_time_smart("workday 09:00 - t", fixed_now)
    assert dt3.strftime("%d.%m %H:%M") == "01.12 09:00"

    dt4, _ = main_module.parse_date_time_smart("выходные - t", fixed_now)
    assert dt4.strftime("%d.%m %H:%M") == "29.11 11:00"

    dt5, _ = main_module.parse_date_time_smart("будний день 09:00 - t", fixed_now)
    assert dt5.strftime("%d.%m %H:%M") == "01.12 09:00"