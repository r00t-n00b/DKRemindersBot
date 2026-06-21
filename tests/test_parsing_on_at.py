def test_on_thursday(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart(
        "on thursday at 20:30 - test",
        fixed_now,
    )
    assert dt.strftime("%H:%M") == "20:30"
    assert text == "test"


def test_on_25_december(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart(
        "on 25 december at 20:30 - test",
        fixed_now,
    )
    assert dt.day == 25
    assert dt.month == 12
    assert dt.strftime("%H:%M") == "20:30"
    assert text == "test"


def test_ru_v_chetverg(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart(
        "в четверг в 20.30 - test",
        fixed_now,
    )
    assert dt.strftime("%H:%M") == "20:30"
    assert text == "test"

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


def test_on_january_25_at_time(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart(
        "on January 25 at 20:30 - test",
        fixed_now,
    )
    assert text == "test"
    assert dt.strftime("%d.%m %H:%M") == "25.01 20:30"