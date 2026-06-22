import main
from parser_normalization import _normalize_on_at_phrase


def test_normalize_on_at_phrase_removes_english_on_and_at():
    assert _normalize_on_at_phrase("on thursday at 20:30") == "thursday 20:30"


def test_normalize_on_at_phrase_removes_leading_russian_v():
    assert _normalize_on_at_phrase("в четверг 20:30") == "четверг 20:30"


def test_normalize_on_at_phrase_converts_dot_time_when_not_date():
    assert _normalize_on_at_phrase("thursday 20.30") == "thursday 20:30"


def test_normalize_on_at_phrase_keeps_date_like_token():
    assert _normalize_on_at_phrase("02.02 12:00") == "02.02 12:00"


def test_normalize_on_at_phrase_collapses_spaces():
    assert _normalize_on_at_phrase("on   friday   at   20:30") == "friday 20:30"


def test_main_reexports_normalize_on_at_phrase_for_existing_callers():
    assert main._normalize_on_at_phrase is _normalize_on_at_phrase
