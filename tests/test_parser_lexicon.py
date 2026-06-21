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
