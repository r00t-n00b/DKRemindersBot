from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")


def test_parse_weekly_without_weekday_defaults_to_today_weekday(main_module):
    now = datetime(2026, 6, 15, 11, 19, tzinfo=TZ)  # Monday

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "каждую неделю - проверить фильтр",
        now,
    )

    assert first_dt == datetime(2026, 6, 22, 10, 0, tzinfo=TZ)
    assert text == "проверить фильтр"
    assert pattern_type == "weekly"
    assert payload == {"weekday": 0}
    assert (hour, minute) == (10, 0)


def test_parse_weekly_with_time_defaults_to_today_weekday(main_module):
    now = datetime(2026, 6, 15, 11, 19, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "каждую неделю в 12:00 - проверить фильтр",
        now,
    )

    assert first_dt == datetime(2026, 6, 15, 12, 0, tzinfo=TZ)
    assert text == "проверить фильтр"
    assert pattern_type == "weekly"
    assert payload == {"weekday": 0}
    assert (hour, minute) == (12, 0)


def test_parse_every_week_alias(main_module):
    now = datetime(2026, 6, 15, 9, 19, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "every week - check filter",
        now,
    )

    assert first_dt == datetime(2026, 6, 15, 10, 0, tzinfo=TZ)
    assert text == "check filter"
    assert pattern_type == "weekly"
    assert payload == {"weekday": 0}
    assert (hour, minute) == (10, 0)


def test_parse_biweekly_ru_alias(main_module):
    now = datetime(2026, 6, 15, 11, 19, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "раз в две недели - проверить фильтр",
        now,
    )

    assert first_dt == datetime(2026, 6, 29, 10, 0, tzinfo=TZ)
    assert text == "проверить фильтр"
    assert pattern_type == "interval"
    assert payload == {"value": 2, "unit": "weeks"}
    assert (hour, minute) == (10, 0)


def test_parse_biweekly_en_alias(main_module):
    now = datetime(2026, 6, 15, 11, 19, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "every other week - check filter",
        now,
    )

    assert first_dt == datetime(2026, 6, 29, 10, 0, tzinfo=TZ)
    assert text == "check filter"
    assert pattern_type == "interval"
    assert payload == {"value": 2, "unit": "weeks"}
    assert (hour, minute) == (10, 0)


def test_parse_monthly_without_day_defaults_to_today_day(main_module):
    now = datetime(2026, 6, 15, 11, 19, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "каждый месяц - новый джонкейк",
        now,
    )

    assert first_dt == datetime(2026, 7, 15, 10, 0, tzinfo=TZ)
    assert text == "новый джонкейк"
    assert pattern_type == "monthly"
    assert payload == {"day": 15}
    assert (hour, minute) == (10, 0)


def test_parse_monthly_with_time_defaults_to_today_day(main_module):
    now = datetime(2026, 6, 15, 11, 19, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "каждый месяц в 12:00 - новый джонкейк",
        now,
    )

    assert first_dt == datetime(2026, 6, 15, 12, 0, tzinfo=TZ)
    assert text == "новый джонкейк"
    assert pattern_type == "monthly"
    assert payload == {"day": 15}
    assert (hour, minute) == (12, 0)


def test_parse_monthly_first_day_ru_numeric(main_module):
    now = datetime(2026, 6, 15, 11, 19, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "1 числа каждого месяца - новый джонкейк",
        now,
    )

    assert first_dt == datetime(2026, 7, 1, 10, 0, tzinfo=TZ)
    assert text == "новый джонкейк"
    assert pattern_type == "monthly"
    assert payload == {"day": 1}
    assert (hour, minute) == (10, 0)


def test_parse_monthly_first_day_ru_word(main_module):
    now = datetime(2026, 6, 15, 11, 19, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "первого числа каждого месяца - новый джонкейк",
        now,
    )

    assert first_dt == datetime(2026, 7, 1, 10, 0, tzinfo=TZ)
    assert text == "новый джонкейк"
    assert pattern_type == "monthly"
    assert payload == {"day": 1}
    assert (hour, minute) == (10, 0)


def test_parse_monthly_aliases_en(main_module):
    now = datetime(2026, 6, 15, 9, 19, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "monthly - new johncake",
        now,
    )

    assert first_dt == datetime(2026, 6, 15, 10, 0, tzinfo=TZ)
    assert text == "new johncake"
    assert pattern_type == "monthly"
    assert payload == {"day": 15}
    assert (hour, minute) == (10, 0)


def test_parse_every_first_of_month_en(main_module):
    now = datetime(2026, 6, 15, 11, 19, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "every 1st of the month - new johncake",
        now,
    )

    assert first_dt == datetime(2026, 7, 1, 10, 0, tzinfo=TZ)
    assert text == "new johncake"
    assert pattern_type == "monthly"
    assert payload == {"day": 1}
    assert (hour, minute) == (10, 0)


def test_parse_yearly_without_date_defaults_to_today_date(main_module):
    now = datetime(2026, 6, 15, 11, 19, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "каждый год - проверить страховку",
        now,
    )

    assert first_dt == datetime(2027, 6, 15, 10, 0, tzinfo=TZ)
    assert text == "проверить страховку"
    assert pattern_type == "yearly"
    assert payload == {"month": 6, "day": 15}
    assert (hour, minute) == (10, 0)


def test_parse_yearly_alias_en(main_module):
    now = datetime(2026, 6, 15, 9, 19, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "yearly - check insurance",
        now,
    )

    assert first_dt == datetime(2026, 6, 15, 10, 0, tzinfo=TZ)
    assert text == "check insurance"
    assert pattern_type == "yearly"
    assert payload == {"month": 6, "day": 15}
    assert (hour, minute) == (10, 0)

def test_parse_weekdays_alias_en(main_module):
    now = datetime(2026, 6, 13, 11, 19, tzinfo=TZ)  # Saturday

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "weekdays - check reports",
        now,
    )

    assert first_dt == datetime(2026, 6, 15, 10, 0, tzinfo=TZ)
    assert text == "check reports"
    assert pattern_type == "weekly_multi"
    assert payload == {"days": [0, 1, 2, 3, 4]}
    assert (hour, minute) == (10, 0)


def test_parse_weekends_alias_en(main_module):
    now = datetime(2026, 6, 15, 11, 19, tzinfo=TZ)  # Monday

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "weekends - check reports",
        now,
    )

    assert first_dt == datetime(2026, 6, 20, 10, 0, tzinfo=TZ)
    assert text == "check reports"
    assert pattern_type == "weekly_multi"
    assert payload == {"days": [5, 6]}
    assert (hour, minute) == (10, 0)


def test_parse_po_budnyam_alias_ru(main_module):
    now = datetime(2026, 6, 13, 11, 19, tzinfo=TZ)  # Saturday

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "по будням - проверить отчеты",
        now,
    )

    assert first_dt == datetime(2026, 6, 15, 10, 0, tzinfo=TZ)
    assert text == "проверить отчеты"
    assert pattern_type == "weekly_multi"
    assert payload == {"days": [0, 1, 2, 3, 4]}
    assert (hour, minute) == (10, 0)


def test_parse_po_vyhodnym_alias_ru(main_module):
    now = datetime(2026, 6, 15, 11, 19, tzinfo=TZ)  # Monday

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "по выходным - проверить отчеты",
        now,
    )

    assert first_dt == datetime(2026, 6, 20, 10, 0, tzinfo=TZ)
    assert text == "проверить отчеты"
    assert pattern_type == "weekly_multi"
    assert payload == {"days": [5, 6]}
    assert (hour, minute) == (10, 0)

def test_monthly_next_occurrence_clamps_31_to_short_month(main_module):
    after_dt = datetime(2026, 1, 31, 10, 1, tzinfo=TZ)

    next_dt = main_module.compute_next_occurrence(
        "monthly",
        {"day": 31},
        10,
        0,
        after_dt,
    )

    assert next_dt == datetime(2026, 2, 28, 10, 0, tzinfo=TZ)


def test_monthly_next_occurrence_clamps_31_to_30_day_month(main_module):
    after_dt = datetime(2026, 3, 31, 10, 1, tzinfo=TZ)

    next_dt = main_module.compute_next_occurrence(
        "monthly",
        {"day": 31},
        10,
        0,
        after_dt,
    )

    assert next_dt == datetime(2026, 4, 30, 10, 0, tzinfo=TZ)


def test_monthly_next_occurrence_keeps_31_when_month_has_31_days(main_module):
    after_dt = datetime(2026, 4, 30, 10, 1, tzinfo=TZ)

    next_dt = main_module.compute_next_occurrence(
        "monthly",
        {"day": 31},
        10,
        0,
        after_dt,
    )

    assert next_dt == datetime(2026, 5, 31, 10, 0, tzinfo=TZ)

def test_looks_like_recurring_for_ru_monthly_ordinal_phrases(main_module):
    assert main_module.looks_like_recurring("третьего числа каждого месяца - новый джонкейк")
    assert main_module.looks_like_recurring("четырнадцатого числа каждого месяца - новый джонкейк")
    assert main_module.looks_like_recurring("тридцать первого числа каждого месяца - новый джонкейк")


def test_parse_monthly_third_day_ru_word(main_module):
    now = datetime(2026, 6, 15, 15, 18, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "третьего числа каждого месяца - новый джонкейк",
        now,
    )

    assert first_dt == datetime(2026, 7, 3, 10, 0, tzinfo=TZ)
    assert text == "новый джонкейк"
    assert pattern_type == "monthly"
    assert payload == {"day": 3}
    assert (hour, minute) == (10, 0)


def test_parse_monthly_fourteenth_day_ru_word(main_module):
    now = datetime(2026, 6, 15, 15, 18, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "четырнадцатого числа каждого месяца - новый джонкейк",
        now,
    )

    assert first_dt == datetime(2026, 7, 14, 10, 0, tzinfo=TZ)
    assert text == "новый джонкейк"
    assert pattern_type == "monthly"
    assert payload == {"day": 14}
    assert (hour, minute) == (10, 0)


def test_parse_monthly_thirty_first_day_ru_compound_word(main_module):
    now = datetime(2026, 6, 15, 15, 18, tzinfo=TZ)

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "тридцать первого числа каждого месяца - новый джонкейк",
        now,
    )

    assert first_dt == datetime(2026, 6, 30, 10, 0, tzinfo=TZ)
    assert text == "новый джонкейк"
    assert pattern_type == "monthly"
    assert payload == {"day": 31}
    assert (hour, minute) == (10, 0)

