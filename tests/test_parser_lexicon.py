import parser_lexicon as lex


def test_simple_recurring_aliases_are_first_tokens_for_routing(main_module):
    for alias in lex.RECURRING_SIMPLE_ALIASES:
        assert alias in lex.RECURRING_FIRST_TOKENS
        assert main_module.looks_like_recurring(f"{alias} - smoke")


def test_simple_recurring_aliases_are_missing_dash_candidates():
    for alias in lex.RECURRING_SIMPLE_ALIASES:
        assert lex.is_recurring_missing_dash_candidate(f"{alias} smoke")

    assert lex.is_recurring_missing_dash_candidate("every day smoke")
    assert lex.is_recurring_missing_dash_candidate("каждый день smoke")
    assert not lex.is_recurring_missing_dash_candidate("tomorrow smoke")


def test_date_lexicon_is_shared_with_main(main_module):
    assert main_module.WEEKDAY_EN is lex.WEEKDAY_EN
    assert main_module.WEEKDAY_RU is lex.WEEKDAY_RU
    assert main_module.MONTH_EN is lex.MONTH_EN


def test_date_lexicon_still_supports_existing_date_parsing(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart("next monday 18:00 - test en weekday", fixed_now)
    assert text == "test en weekday"
    assert dt.weekday() == lex.WEEKDAY_EN["monday"]
    assert dt.hour == 18
    assert dt.minute == 0

    dt, text = main_module.parse_date_time_smart("следующий понедельник 18:00 - test ru weekday", fixed_now)
    assert text == "test ru weekday"
    assert dt.weekday() == lex.WEEKDAY_RU["понедельник"]
    assert dt.hour == 18
    assert dt.minute == 0

    dt, text = main_module.parse_date_time_smart("january 25 20:30 - test month", fixed_now)
    assert text == "test month"
    assert dt.month == lex.MONTH_EN["january"]
    assert dt.day == 25
    assert dt.hour == 20
    assert dt.minute == 30


def test_remaining_lexicon_blocks_are_shared_with_main(main_module):
    assert main_module.NEXT_WORDS is lex.NEXT_WORDS
    assert main_module.THIS_WORDS is lex.THIS_WORDS
    assert main_module.ORDINAL_RU is lex.ORDINAL_RU
    assert main_module.ORDINAL_RU_COMPOUND_TENS is lex.ORDINAL_RU_COMPOUND_TENS
    assert main_module.VOICE_SPOKEN_NUMBER_REPLACEMENTS is lex.VOICE_SPOKEN_NUMBER_REPLACEMENTS
    assert main_module.VOICE_RU_MONTH_NORMALIZATION_MAP is lex.VOICE_RU_MONTH_NORMALIZATION_MAP
    assert main_module.INTERVAL_UNITS_EN is lex.INTERVAL_UNITS_EN
    assert main_module.INTERVAL_UNITS_RU is lex.INTERVAL_UNITS_RU
    assert main_module.MONTH_RU is lex.MONTH_RU


def test_remaining_lexicon_still_supports_existing_parser_behaviour(main_module, fixed_now):
    dt, text = main_module.parse_date_time_smart("next monday 18:00 - next word", fixed_now)
    assert text == "next word"
    assert dt.weekday() == lex.WEEKDAY_EN["monday"]
    assert dt.hour == 18
    assert dt.minute == 0

    dt, text = main_module.parse_date_time_smart("coming monday 18:00 - this word", fixed_now)
    assert text == "this word"
    assert dt.weekday() == lex.WEEKDAY_EN["monday"]
    assert dt.hour == 18
    assert dt.minute == 0

    dt, text = main_module.parse_date_time_smart("25 января 20:30 - ru month", fixed_now)
    assert text == "ru month"
    assert dt.month == lex.MONTH_RU["января"]
    assert dt.day == 25
    assert dt.hour == 20
    assert dt.minute == 30

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "двадцать первое число каждого месяца 10:00 - ordinal ru",
        fixed_now,
    )
    assert text == "ordinal ru"
    assert pattern_type == "monthly"
    assert payload == {"day": 21}
    assert hour == 10
    assert minute == 0
    assert first_dt.day == 21

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "every 3 days - interval en",
        fixed_now,
    )
    assert text == "interval en"
    assert pattern_type == "interval"
    assert payload == {"value": 3, "unit": "days"}

    first_dt, text, pattern_type, payload, hour, minute = main_module.parse_recurring(
        "каждые 2 часа - interval ru",
        fixed_now,
    )
    assert text == "interval ru"
    assert pattern_type == "interval"
    assert payload == {"value": 2, "unit": "hours"}

    normalized = main_module._normalize_voice_spoken_numbers(
        "двадцать девятого мая в восемнадцать сорок шесть"
    )
    assert "29" in normalized
    assert "18" in normalized
    assert "46" in normalized

    normalized_month = main_module._normalize_voice_ru_months("двадцать девятого мая")
    assert "may" in normalized_month
