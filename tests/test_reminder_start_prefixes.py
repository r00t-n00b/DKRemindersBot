from dkreminders_bot.utils.command_text import (
    first_token_looks_like_reminder_start,
    maybe_split_alias_first_token,
)


def test_na_is_valid_reminder_start_prefix():
    assert first_token_looks_like_reminder_start("на") is True


def test_na_sleduyushchey_nedele_is_not_treated_as_alias():
    alias, args = maybe_split_alias_first_token(
        "на следующей неделе забрать коляску"
    )

    assert alias is None
    assert args == "на следующей неделе забрать коляску"
