import main
from command_text import (
    MONTH_REMINDER_PREFIXES,
    SMART_REMINDER_PREFIXES,
    extract_after_command,
    first_token_looks_like_reminder_start,
    maybe_split_alias_first_token,
)


def test_extract_after_command_preserves_bulk_newlines_after_command():
    assert extract_after_command("/remind   first\nsecond") == "first\nsecond"


def test_extract_after_command_returns_stripped_plain_text_when_not_command():
    assert extract_after_command("  tomorrow 10:00 - test  ") == "tomorrow 10:00 - test"


def test_extract_after_command_returns_empty_for_command_without_args():
    assert extract_after_command("/remind") == ""


def test_first_token_looks_like_reminder_start_for_time_date_words_and_months():
    assert first_token_looks_like_reminder_start("10:30")
    assert first_token_looks_like_reminder_start("25.06")
    assert first_token_looks_like_reminder_start("tomorrow")
    assert first_token_looks_like_reminder_start("завтра")
    assert first_token_looks_like_reminder_start("january")
    assert not first_token_looks_like_reminder_start("family")


def test_maybe_split_alias_first_token_extracts_alias_from_first_line():
    alias, args = maybe_split_alias_first_token("family завтра 10:00\nкупить молоко")

    assert alias == "family"
    assert args == "завтра 10:00\nкупить молоко"


def test_maybe_split_alias_first_token_does_not_extract_alias_for_date_or_time_prefix():
    assert maybe_split_alias_first_token("25.06 купить молоко") == (None, "25.06 купить молоко")
    assert maybe_split_alias_first_token("10:30 купить молоко") == (None, "10:30 купить молоко")
    assert maybe_split_alias_first_token("january 25 buy milk") == (None, "january 25 buy milk")
    assert maybe_split_alias_first_token("25 january buy milk") == (None, "25 january buy milk")


def test_maybe_split_alias_first_token_does_not_extract_alias_for_dash_prefix():
    assert maybe_split_alias_first_token("- купить молоко") == (None, "- купить молоко")


def test_main_reexports_command_text_helpers_for_existing_callers():
    assert main.extract_after_command is extract_after_command
    assert main.first_token_looks_like_reminder_start is first_token_looks_like_reminder_start
    assert main.maybe_split_alias_first_token is maybe_split_alias_first_token
    assert main.SMART_REMINDER_PREFIXES is SMART_REMINDER_PREFIXES
    assert main.MONTH_REMINDER_PREFIXES is MONTH_REMINDER_PREFIXES
