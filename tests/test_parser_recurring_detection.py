import main
from dkreminders_bot.parsing.parser_recurring_detection import looks_like_recurring


def test_looks_like_recurring_detects_first_tokens():
    assert looks_like_recurring("every monday 10:00 - check")
    assert looks_like_recurring("каждый понедельник 10:00 - проверить")


def test_looks_like_recurring_detects_non_first_token_patterns():
    assert looks_like_recurring("15 число каждый месяц - оплатить")
    assert looks_like_recurring("по будням - пить воду")
    assert looks_like_recurring("раз в две недели - проверить")
    assert looks_like_recurring("on the 15th of every month - pay rent")
    assert looks_like_recurring("15th of every month - pay rent")


def test_looks_like_recurring_rejects_one_off_text():
    assert not looks_like_recurring("")
    assert not looks_like_recurring("tomorrow 10:00 buy milk")
    assert not looks_like_recurring("15.07 10:00 buy milk")


def test_main_reexports_looks_like_recurring_for_existing_callers():
    assert main.looks_like_recurring is looks_like_recurring
