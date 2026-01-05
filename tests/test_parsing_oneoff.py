from datetime import timedelta


def test_split_expr_and_text(main_module):
    expr, text = main_module._split_expr_and_text("29.11 10:00 - hello")
    assert expr == "29.11 10:00"
    assert text == "hello"


def test_absolute_date_time(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart("29.11 12:00 - hello", fixed_now)
    assert text == "hello"
    assert dt.strftime("%d.%m %H:%M") == "29.11 12:00"


def test_absolute_date_default_time(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart("29.11 - hi", fixed_now)
    assert text == "hi"
    assert dt.strftime("%d.%m %H:%M") == "29.11 11:00"


def test_time_only_today_or_tomorrow(main_module, fixed_now):
    dt, _ = main_module.parse_date_time_smart("23:59 - t", fixed_now)
    assert dt.date() == fixed_now.date()
    assert dt.strftime("%H:%M") == "23:59"

    dt2, _ = main_module.parse_date_time_smart("09:00 - t", fixed_now)
    assert dt2.date() == (fixed_now.date() + timedelta(days=1))
    assert dt2.strftime("%H:%M") == "09:00"


def test_in_expression(main_module, fixed_now):
    dt, _ = main_module.parse_date_time_smart("in 2 hours - t", fixed_now)
    assert dt == fixed_now + timedelta(hours=2)

    dt2, _ = main_module.parse_date_time_smart("через 45 минут - t", fixed_now)
    assert dt2 == fixed_now + timedelta(minutes=45)


def test_today_tomorrow_poslezavtra(main_module, fixed_now):
    dt, _ = main_module.parse_date_time_smart("today 18:00 - t", fixed_now)
    assert dt.strftime("%d.%m %H:%M") == "28.11 18:00"

    dt2, _ = main_module.parse_date_time_smart("tomorrow - t", fixed_now)
    assert dt2.strftime("%d.%m %H:%M") == "29.11 11:00"

    dt3, _ = main_module.parse_date_time_smart("day after tomorrow 10:00 - t", fixed_now)
    assert dt3.strftime("%d.%m %H:%M") == "30.11 10:00"

    dt4, _ = main_module.parse_date_time_smart("послезавтра - t", fixed_now)
    assert dt4.strftime("%d.%m %H:%M") == "30.11 11:00"