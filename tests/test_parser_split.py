import pytest

import main
from dkreminders_bot.parsing.parser_split import _split_expr_and_text


def test_split_expr_and_text_dash_format():
    assert _split_expr_and_text("tomorrow 10:00 - buy milk") == ("tomorrow 10:00", "buy milk")


def test_split_expr_and_text_date_time_without_dash():
    assert _split_expr_and_text("22.06 19:30 buy milk") == ("22.06 19:30", "buy milk")


def test_split_expr_and_text_russian_month_date_without_dash():
    assert _split_expr_and_text("1 октября в 12:30 проверить документы") == (
        "1 октября в 12:30",
        "проверить документы",
    )


def test_split_expr_and_text_english_month_date_without_dash():
    assert _split_expr_and_text("March 14 10:30 check printer") == (
        "March 14 10:30",
        "check printer",
    )


def test_split_expr_and_text_rejects_unparseable_text():
    with pytest.raises(ValueError):
        _split_expr_and_text("just random words without date")


def test_main_reexports_split_expr_and_text_for_existing_callers():
    assert main._split_expr_and_text is _split_expr_and_text
