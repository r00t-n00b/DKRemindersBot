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
