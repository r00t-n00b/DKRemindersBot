import pytest


def test_looks_like_recurring(main_module):
    assert main_module.looks_like_recurring("every day 10:00 - a")
    assert main_module.looks_like_recurring("каждый день 10:00 - a")
    assert not main_module.looks_like_recurring("29.11 10:00 - a")


def test_recurring_every_day_en(main_module, fixed_now):
    first_dt, text, ptype, payload, h, m = main_module.parse_recurring("every day 10:00 - a", fixed_now)
    assert text == "a"
    assert ptype == "daily"
    assert payload == {}
    assert (h, m) == (10, 0)
    assert first_dt.strftime("%d.%m %H:%M") == "29.11 10:00"


def test_recurring_each_day_ru_regression(main_module, fixed_now):
    # ключевой тест на баг "каждый день"
    first_dt, text, ptype, payload, h, m = main_module.parse_recurring("каждый день 10:00 - a", fixed_now)
    assert ptype == "daily"
    assert (h, m) == (10, 0)
    assert text == "a"


def test_recurring_weekly_en_ru(main_module, fixed_now):
    _, _, ptype, payload, _, _ = main_module.parse_recurring("every Monday 10:00 - a", fixed_now)
    assert ptype == "weekly"
    assert payload["weekday"] == 0

    _, _, ptype2, payload2, _, _ = main_module.parse_recurring("каждый понедельник 10:00 - a", fixed_now)
    assert ptype2 == "weekly"
    assert payload2["weekday"] == 0

    _, _, ptype3, payload3, _, _ = main_module.parse_recurring("каждую среду 19:00 - a", fixed_now)
    assert ptype3 == "weekly"
    assert payload3["weekday"] == 2


def test_recurring_weekday_weekend(main_module, fixed_now):
    _, _, ptype, payload, _, _ = main_module.parse_recurring("every weekday 09:00 - a", fixed_now)
    assert ptype == "weekly_multi"
    assert payload["days"] == [0, 1, 2, 3, 4]

    _, _, ptype2, payload2, _, _ = main_module.parse_recurring("every weekend 11:00 - a", fixed_now)
    assert ptype2 == "weekly_multi"
    assert payload2["days"] == [5, 6]

    _, _, ptype3, payload3, _, _ = main_module.parse_recurring("каждые выходные 11:00 - a", fixed_now)
    assert ptype3 == "weekly_multi"
    assert payload3["days"] == [5, 6]


def test_recurring_monthly(main_module, fixed_now):
    _, _, ptype, payload, h, m = main_module.parse_recurring("every month 15 10:00 - a", fixed_now)
    assert ptype == "monthly"
    assert payload["day"] == 15
    assert (h, m) == (10, 0)

    _, _, ptype2, payload2, h2, m2 = main_module.parse_recurring("каждый месяц 15 10:00 - a", fixed_now)
    assert ptype2 == "monthly"
    assert payload2["day"] == 15
    assert (h2, m2) == (10, 0)


def test_recurring_invalid(main_module, fixed_now):
    with pytest.raises(ValueError):
        main_module.parse_recurring("every month 40 10:00 - a", fixed_now)